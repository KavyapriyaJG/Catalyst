import json
import urllib.error
import urllib.request
from typing import Any

from backlog_generation.epic_agent import JiraEpicOutput, JiraStoriesOutput, generate_stories_from_epic
from backlog_generation.jira import (
    build_jira_bulk_epics_payload,
    build_jira_bulk_story_payload,
    jira_auth_header,
    jira_bulk_endpoint,
)
from config import get_settings


class JiraPublishError(Exception):
    """Raised when the Jira bulk-publish API returns an error."""

    def __init__(self, status_code: int, detail: Any):
        self.status_code = status_code
        self.detail = detail
        super().__init__(str(detail))


def generate_stories(
    epic: JiraEpicOutput,
    story_count: int,
    backlog_id: str | None = None,
    epic_record_id: str | None = None,
) -> JiraStoriesOutput:
    """Generate Jira stories from an epic payload and optionally persist them."""
    stories_data = generate_stories_from_epic(epic.model_dump(), story_count)
    validated = JiraStoriesOutput(**stories_data)

    if backlog_id and epic_record_id and validated.stories:
        from api.services import backlog_service  # late import to avoid circular
        backlog_service.persist_saved_stories(epic_record_id, validated.stories)

    return validated


def publish_to_jira(
    epics_payload: Any | None,
    stories_payload: Any | None,
    issue_type: str,
    parent_key: str | None,
    epic_record_id: str | None = None,
    story_record_ids: list[str] | None = None,
) -> tuple[list, list]:
    """Build and POST a bulk-create payload to the Jira API.

    Args:
        epics_payload:  JiraEpicsResponse-like object (has `.epics`), used when issue_type == "epic".
        stories_payload: JiraStoriesResponse-like object (has `.stories`), used when issue_type == "story".
        issue_type: "epic" or "story".
        parent_key: Optional Jira parent key to link stories to.
        epic_record_id: Optional DB record ID for the epic being published (type=epic).
        story_record_ids: Optional list of DB record IDs for stories being published (type=story).

    Returns:
        Tuple of (issues, errors) lists from the Jira response.

    Raises:
        ValueError: If payload building fails.
        JiraPublishError: If Jira returns an HTTP error.
        ConnectionError: If the Jira host is unreachable.
    """
    if issue_type == "story":
        jira_bulk_payload = build_jira_bulk_story_payload(
            stories_payload.stories, parent_key=parent_key
        )
    else:
        jira_bulk_payload = build_jira_bulk_epics_payload(epics_payload.epics)

    request = urllib.request.Request(
        jira_bulk_endpoint(),
        data=json.dumps(jira_bulk_payload).encode("utf-8"),
        headers={
            "Authorization": jira_auth_header(),
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=get_settings().JIRA_FETCH_TIMEOUT) as response:
            jira_response = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        error_body = error.read().decode("utf-8", errors="ignore")
        try:
            detail = json.loads(error_body) if error_body else {"message": error.reason}
        except json.JSONDecodeError:
            detail = {"message": error_body or str(error.reason)}
        raise JiraPublishError(status_code=error.code, detail=detail) from error
    except urllib.error.URLError as error:
        raise ConnectionError(f"Failed to reach Jira: {error.reason}") from error
    except json.JSONDecodeError as error:
        raise ConnectionError(f"Invalid JSON response from Jira: {error}") from error

    if not isinstance(jira_response, dict):
        raise ConnectionError("Unexpected Jira response format.")

    issues: list = jira_response.get("issues", [])
    errors: list = jira_response.get("errors", [])

    # Persist jira_key back to DB records that were successfully created.
    if not errors:
        from api.services import backlog_service  # late import to avoid circular

        if issue_type == "epic" and epic_record_id and issues:
            # A bulk epic create returns one issue per epic; handle first key.
            first_key = issues[0].get("key") if issues else None
            if first_key:
                try:
                    backlog_service.publish_epic(epic_record_id, first_key)
                except Exception:
                    pass  # best-effort; do not fail the whole publish

        elif issue_type == "story" and story_record_ids and issues:
            for record_id, issue in zip(story_record_ids, issues):
                key = issue.get("key")
                if key:
                    try:
                        backlog_service.publish_story(record_id, key)
                    except Exception:
                        pass  # best-effort

    return issues, errors
