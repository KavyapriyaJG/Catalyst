from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from api.models import (
    JiraBulkPublishResponse,
    JiraEpicsResponse,
    JiraStoriesRequest,
    JiraStoriesResponse,
)
from api.services.story_service import JiraPublishError, generate_stories, publish_to_jira

router = APIRouter(tags=["jira-stories"])


@router.post("/jira/stories", response_model=JiraStoriesResponse)
def run_jira_story_agent(payload: JiraStoriesRequest):
    try:
        validated_stories = generate_stories(payload.epic, payload.story_count)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"Story generation failed: {error}") from error

    return JiraStoriesResponse(stories=validated_stories)


@router.post("/jira/publish/issues", response_model=JiraBulkPublishResponse)
def publish_issues_to_jira(
    payload: JiraEpicsResponse | JiraStoriesResponse,
    issue_type: Literal["epic", "story"] = Query(default="epic", alias="type"),
    parent_key: str | None = Query(default=None, alias="parent-key"),
):
    if issue_type == "story":
        if not isinstance(payload, JiraStoriesResponse):
            raise HTTPException(
                status_code=400,
                detail="For type=story, payload must include a `stories` object.",
            )
        if not payload.stories.stories:
            raise HTTPException(status_code=400, detail="`stories.stories` cannot be empty.")
    else:
        if not isinstance(payload, JiraEpicsResponse):
            raise HTTPException(
                status_code=400,
                detail="For type=epic, payload must include an `epics` array.",
            )
        if not payload.epics:
            raise HTTPException(status_code=400, detail="`epics` cannot be empty.")

    try:
        issues, errors = publish_to_jira(
            epics_payload=payload if isinstance(payload, JiraEpicsResponse) else None,
            stories_payload=payload if isinstance(payload, JiraStoriesResponse) else None,
            issue_type=issue_type,
            parent_key=parent_key,
        )
    except JiraPublishError as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from error
    except ConnectionError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"Jira publish failed: {error}") from error

    return JiraBulkPublishResponse(issues=issues, errors=errors)
