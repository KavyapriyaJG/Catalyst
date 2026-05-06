import json
import urllib.error
import urllib.request
from typing import Any

from backlog_generation.epic_agent import JiraEpicOutput, JiraStoriesOutput, generate_stories_from_epic
from backlog_generation.utils.jira_utils import (
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


def generate_stories(epic: JiraEpicOutput, story_count: int) -> JiraStoriesOutput:
    """Generate Jira stories from an epic payload."""
    stories_data = generate_stories_from_epic(epic.model_dump(), story_count)
    return JiraStoriesOutput(**stories_data)


def publish_to_jira(
    epics_payload: Any | None,
    stories_payload: Any | None,
    issue_type: str,
    parent_key: str | None,
) -> tuple[list, list]:
    """Build and POST a bulk-create payload to the Jira API.

    Args:
        epics_payload:  JiraEpicsResponse-like object (has `.epics`), used when issue_type == "epic".
        stories_payload: JiraStoriesResponse-like object (has `.stories`), used when issue_type == "story".
        issue_type: "epic" or "story".
        parent_key: Optional Jira parent key to link stories to.

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

    return jira_response.get("issues", []), jira_response.get("errors", [])
