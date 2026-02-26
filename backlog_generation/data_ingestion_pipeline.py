import base64
import json
import os
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass

from dotenv import load_dotenv
from psycopg import Connection, connect

load_dotenv()


@dataclass(slots=True)
class JiraIssueRecord:
    issue_id: str
    issue_key: str
    summary: str
    description: str


def get_from_env(name: str, default: any = None) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        if default is None:
            raise ValueError(f"Missing required environment variable: {name}")
        return default
    return value


def _jira_auth_header() -> str:
    username = get_from_env("JIRA_USERNAME")
    token = get_from_env("JIRA_AUTH_TOKEN")
    encoded = base64.b64encode(f"{username}:{token}".encode("utf-8")).decode("utf-8")
    return f"Basic {encoded}"


def jira_base_url() -> str:
    return get_from_env("JIRA_BASE_URL").rstrip("/")


# def jql_query() -> str:
#     base_jql = os.getenv("JIRA_JQL", "").strip()
#     created_bound = "created >= -365d"

#     if not base_jql:
#         return f"{created_bound} ORDER BY created DESC"

#     order_match = re.search(r"\border\s+by\b", base_jql, flags=re.IGNORECASE)
#     if not order_match:
#         return f"({base_jql}) AND {created_bound}"

#     order_index = order_match.start()
#     filters = base_jql[:order_index].strip()
#     order_by = base_jql[order_index:].strip()
#     if not filters:
#         return f"{created_bound} {order_by}"
#     return f"({filters}) AND {created_bound} {order_by}"


def fetch_issues_from_jira(start_at: int, batch_size: int) -> tuple[list[JiraIssueRecord], int, bool]:
    base_url = jira_base_url()
    fetch_issues_endpoint = "rest/api/3/search/jql"
    fields_to_include = ["summary", "description"]

    params = {
        "jql": get_from_env("JIRA_FETCH_ISSUES_JQL", "project=TEST AND created>=-365d ORDER BY created DESC"),
        "startAt": str(start_at),
        "maxResults": str(batch_size),
        "fields": ",".join(fields_to_include),
    }

    query = urllib.parse.urlencode(params)
    url = f"{base_url}/{fetch_issues_endpoint}?{query}"
    print(url)

    request = urllib.request.Request(
        url,
        headers={
            "Authorization": _jira_auth_header(),
            "Accept": "application/json",
        },
        method="GET",
    )

    with urllib.request.urlopen(request, timeout=60) as response:
        result = json.loads(response.read().decode("utf-8"))

    issues = result.get("issues", [])
    count = len(issues)
    isLast = bool(result.get("isLast", True))

    records: list[JiraIssueRecord] = []
    for issue in issues:
        fields = issue.get("fields") or {}
        summary = fields.get("summary") or ""
        description_value = fields.get("description")

        if isinstance(description_value, str):
            description = description_value
        elif description_value is None:
            description = ""
        else:
            description = json.dumps(description_value, ensure_ascii=False)

        records.append(
            JiraIssueRecord(
                issue_id=str(issue.get("id") or ""),
                issue_key=str(issue.get("key") or ""),
                summary=summary,
                description=description,
            )
        )

    has_more = not isLast
    return records, count, has_more


def create_table_if_missing(conn: Connection, table_name: str) -> None:
    with conn.cursor() as cursor:
        cursor.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {table_name} (
                issue_id TEXT PRIMARY KEY,
                issue_key TEXT NOT NULL,
                summary TEXT,
                description TEXT,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
    conn.commit()


def upsert_records_in_db(conn: Connection, table_name: str, records: list[JiraIssueRecord]) -> int:
    if not records:
        return 0

    rows = [
        (record.issue_id, record.issue_key, record.summary, record.description)
        for record in records
        if record.issue_id and record.issue_key
    ]

    if not rows:
        return 0

    query = f"""
        INSERT INTO {table_name} (issue_id, issue_key, summary, description)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (issue_id) DO UPDATE SET
            issue_key = EXCLUDED.issue_key,
            summary = EXCLUDED.summary,
            description = EXCLUDED.description,
            updated_at = NOW()
    """

    with conn.cursor() as cursor:
        cursor.executemany(query, rows)
    conn.commit()

    return len(rows)


def ingest_jira_issues() -> dict:
    batch_size = int(get_from_env("JIRA_BATCH_SIZE", 50))
    table_name = get_from_env("POSTGRES_TABLE", "jira_issues")

    inserted_or_updated = 0
    start_at = 0
    count = total = 0
    batch_count = 0

    postgres_dsn = get_from_env("POSTGRES_DSN")

    with connect(postgres_dsn) as conn:
        create_table_if_missing(conn, table_name)

        has_more = True
        issues_to_be_processed = int(get_from_env("JIRA_ISSUES_TO_BE_PROCESSED_COUNT", 10))

        while has_more and (total < issues_to_be_processed):
            records, count, has_more = fetch_issues_from_jira(start_at=start_at, batch_size=batch_size)
            affected = upsert_records_in_db(conn, table_name, records)

            inserted_or_updated += affected
            batch_count += 1
            start_at += len(records)
            total += count

            if not records:
                break

    return {
        "table": table_name,
        "batch_size": batch_size,
        "batches_processed": batch_count,
        "total_issues": total,
        "rows_upserted": inserted_or_updated,
    }


result = ingest_jira_issues()
print(json.dumps(result, indent=2))
