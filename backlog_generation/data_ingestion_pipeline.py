import base64
import json
import urllib.parse
import urllib.request
from typing import NotRequired, TypedDict

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from backlog_generation.db import engine, get_session
from backlog_generation.models import (
    Base,
    IssueHierarchyRecord as IssueHierarchyORMRecord,
    IssueLinkRecord as IssueLinkORMRecord,
    IssueRecord as IssueORMRecord,
)
from config import get_settings


class IssueLinkUpsertRow(TypedDict):
    source_id: int
    target_id: int
    link_type: str


class LinkedIssueRow(TypedDict):
    id: int
    issue_key: str


class IssueUpsertRow(TypedDict):
    id: int
    issue_key: str
    parent_id: NotRequired[int]
    parent_issue_key: NotRequired[str]
    issue_links: NotRequired[list[IssueLinkUpsertRow]]
    linked_issue_rows: NotRequired[list[LinkedIssueRow]]


def _jira_auth_header() -> str:
    s = get_settings()
    encoded = base64.b64encode(f"{s.JIRA_USERNAME}:{s.JIRA_AUTH_TOKEN}".encode("utf-8")).decode("utf-8")
    return f"Basic {encoded}"


def jira_base_url() -> str:
    return get_settings().JIRA_BASE_URL.rstrip("/")


def parse_issue_id(issue_obj: dict) -> tuple[int | None, str]:
    issue_id_raw = issue_obj.get("id")
    issue_key = issue_obj.get("key") or ""

    try:
        issue_id = int(issue_id_raw) if issue_id_raw is not None else None
    except (TypeError, ValueError):
        issue_id = None

    return issue_id, issue_key


def extract_issuelinks(issue_id: int, issue_links: list[dict]) -> tuple[list[IssueLinkUpsertRow], list[LinkedIssueRow]]:
    link_rows: list[IssueLinkUpsertRow] = []
    linked_issue_rows: list[LinkedIssueRow] = []

    for issue_link in issue_links:
        link_type_data = issue_link.get("type") or {}

        outward_id, outward_key = parse_issue_id(issue_link.get("outwardIssue") or {})
        if outward_id is not None:
            link_rows.append(
                {
                    "source_id": issue_id,
                    "target_id": outward_id,
                    "link_type": link_type_data.get("outward") or link_type_data.get("name") or "related",
                }
            )
            if outward_key:
                linked_issue_rows.append({"id": outward_id, "issue_key": outward_key})

        inward_id, inward_key = parse_issue_id(issue_link.get("inwardIssue") or {})
        if inward_id is not None:
            link_rows.append(
                {
                    "source_id": issue_id,
                    "target_id": inward_id,
                    "link_type": link_type_data.get("inward") or link_type_data.get("name") or "related",
                }
            )
            if inward_key:
                linked_issue_rows.append({"id": inward_id, "issue_key": inward_key})

    return link_rows, linked_issue_rows


def fetch_issues_from_jira(start_at: int, batch_size: int) -> tuple[list[IssueUpsertRow], int, bool]:
    base_url = jira_base_url()
    fetch_issues_endpoint = "rest/api/3/search/jql"
    fields_to_include = ["parent", "subtasks", "issuelinks"]

    params = {
        "jql": get_settings().JIRA_FETCH_ISSUES_JQL,
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

    with urllib.request.urlopen(request, timeout=get_settings().JIRA_FETCH_TIMEOUT) as response:
        result = json.loads(response.read().decode("utf-8"))

    issues = result.get("issues", [])
    count = len(issues)
    isLast = bool(result.get("isLast", True))
    records: list[IssueUpsertRow] = []

    for issue in issues:
        issue_id, issue_key = parse_issue_id(issue)
        fields = issue.get("fields") or {}
        parent = fields.get("parent") or {}
        parent_id, parent_issue_key = parse_issue_id(parent)
        issue_links = fields.get("issuelinks") or []

        if issue_id is not None and issue_key:
            row: IssueUpsertRow = {"id": issue_id, "issue_key": issue_key}
            if parent_id is not None:
                row["parent_id"] = parent_id
                if parent_issue_key:
                    row["parent_issue_key"] = parent_issue_key

            link_rows, linked_issue_rows = extract_issuelinks(issue_id, issue_links)

            if link_rows:
                row["issue_links"] = link_rows
            if linked_issue_rows:
                row["linked_issue_rows"] = linked_issue_rows
            records.append(row)

    has_more = not isLast
    return records, count, has_more


def create_table_if_missing() -> None:
    Base.metadata.create_all(bind=engine)


def upsert_issues_in_db(session: Session, issue_rows: list[dict[str, int | str]]) -> None:
    if not issue_rows:
        return

    deduped_issue_rows = {int(row["id"]): str(row["issue_key"]) for row in issue_rows}
    rows = [{"id": issue_id, "issue_key": issue_key} for issue_id, issue_key in deduped_issue_rows.items()]

    stmt = insert(IssueORMRecord).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=[IssueORMRecord.id],
        set_={"issue_key": stmt.excluded.issue_key},
    )
    session.execute(stmt)


def insert_issue_hierarchy_rows_in_db(session: Session, records: list[IssueUpsertRow]) -> None:
    hierarchy_rows = [
        {"parent_id": row["parent_id"], "child_id": row["id"]}
        for row in records
        if "parent_id" in row
    ]
    if not hierarchy_rows:
        return

    hierarchy_stmt = insert(IssueHierarchyORMRecord).values(hierarchy_rows)
    hierarchy_stmt = hierarchy_stmt.on_conflict_do_nothing(
        index_elements=[IssueHierarchyORMRecord.parent_id, IssueHierarchyORMRecord.child_id],
    )
    session.execute(hierarchy_stmt)


def insert_issue_link_rows_in_db(session: Session, records: list[IssueUpsertRow]) -> None:
    link_rows = [link for row in records for link in row.get("issue_links", [])]
    if not link_rows:
        return

    link_stmt = insert(IssueLinkORMRecord).values(link_rows)
    link_stmt = link_stmt.on_conflict_do_nothing(
        index_elements=[IssueLinkORMRecord.source_id, IssueLinkORMRecord.target_id, IssueLinkORMRecord.link_type],
    )
    session.execute(link_stmt)


def upsert_records_in_db(session: Session, records: list[IssueUpsertRow]) -> int:
    if not records:
        return 0

    issue_rows = [{"id": row["id"], "issue_key": row["issue_key"]} for row in records]
    issue_rows.extend(
        {"id": row["parent_id"], "issue_key": row["parent_issue_key"]}
        for row in records
        if row.get("parent_id") is not None and row.get("parent_issue_key")
    )
    issue_rows.extend(
        {"id": linked_issue["id"], "issue_key": linked_issue["issue_key"]}
        for row in records
        for linked_issue in row.get("linked_issue_rows", [])
        if linked_issue.get("issue_key")
    )

    upsert_issues_in_db(session, issue_rows)
    insert_issue_hierarchy_rows_in_db(session, records)
    insert_issue_link_rows_in_db(session, records)

    return len(records)


def ingest_jira_issues() -> dict:
    s = get_settings()
    batch_size = s.JIRA_BATCH_SIZE
    table_name = IssueORMRecord.__tablename__

    inserted_or_updated = 0
    start_at = 0
    count = total = 0
    batch_count = 0

    create_table_if_missing()

    with get_session() as session:

        has_more = True
        batches_to_be_processed = s.JIRA_BATCHES_TO_BE_PROCESSED_COUNT
        print(f"Processing up to {batches_to_be_processed} batches of issues with batch size {batch_size}...")

        while has_more and (batch_count < batches_to_be_processed):
            print(f"Fetching batch {batch_count + 1} of issues starting at index {start_at}...")
            
            records, count, has_more = fetch_issues_from_jira(start_at=start_at, batch_size=batch_size)
            affected = upsert_records_in_db(session, records)

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
