"""REST endpoints for listing, fetching, deleting backlogs and status transitions."""

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from api.services import backlog_service

router = APIRouter(prefix="/backlog", tags=["backlog"])


class StatusUpdate(BaseModel):
    status: str
    reviewed_by: str | None = None
    review_comment: str | None = None
    submitted_by: str | None = None


class PublishRequest(BaseModel):
    jira_key: str


class StoryIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    story_id: str = Field(default="")
    epic_id: str = Field(default="")
    title: str
    summary: str = Field(default="")
    description: str = Field(default="")
    acceptance_criteria: List[str] = Field(default_factory=list)
    priority: str = Field(default="Medium")
    status: str = Field(default="draft")
    created_at: str | None = Field(default=None)


class StoriesWrapper(BaseModel):
    """Accepts { "stories": [...] } wrapper sent by the UI."""
    model_config = ConfigDict(extra="ignore")
    stories: List[StoryIn]

@router.get("/", summary="List all backlogs")
def list_backlogs():
    return backlog_service.get_all_backlogs()


@router.get("/{backlog_id}", summary="Get backlog with epics and stories")
def get_backlog(backlog_id: str):
    backlog = backlog_service.get_backlog(backlog_id)
    if backlog is None:
        raise HTTPException(status_code=404, detail=f"Backlog {backlog_id!r} not found.")
    return backlog


@router.get(
    "/{backlog_id}/epics/{epic_record_id}",
    summary="Get a single epic with its stories",
)
def get_epic(backlog_id: str, epic_record_id: str):
    epic = backlog_service.get_epic(epic_record_id)
    if epic is None:
        raise HTTPException(status_code=404, detail=f"Epic record {epic_record_id!r} not found.")
    return epic


@router.delete("/{backlog_id}", summary="Delete a backlog and all its records")
def delete_backlog(backlog_id: str):
    found = backlog_service.remove_backlog(backlog_id)
    if not found:
        raise HTTPException(status_code=404, detail=f"Backlog {backlog_id!r} not found.")
    return {"deleted": backlog_id}


@router.get(
    "/{backlog_id}/epics/{epic_record_id}/stories",
    summary="List all stories for an epic",
)
def list_stories(backlog_id: str, epic_record_id: str):
    epic = backlog_service.get_epic(epic_record_id)
    if epic is None:
        raise HTTPException(status_code=404, detail=f"Epic record {epic_record_id!r} not found.")
    return epic.get("stories", [])


@router.get(
    "/{backlog_id}/epics/{epic_record_id}/stories/{story_record_id}",
    summary="Get a single story",
)
def get_story(backlog_id: str, epic_record_id: str, story_record_id: str):
    story = backlog_service.get_story_by_id(story_record_id)
    if story is None:
        raise HTTPException(status_code=404, detail=f"Story record {story_record_id!r} not found.")
    return story


@router.post(
    "/{backlog_id}/epics/{epic_record_id}/publish",
    summary="Mark epic as synced to Jira with its Jira key",
)
def publish_epic(backlog_id: str, epic_record_id: str, body: PublishRequest):
    try:
        updated = backlog_service.publish_epic(epic_record_id, body.jira_key)
    except FileNotFoundError as err:
        raise HTTPException(status_code=404, detail=str(err)) from err
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    return updated


@router.post(
    "/{backlog_id}/epics/{epic_record_id}/stories/{story_record_id}/publish",
    summary="Mark story as synced to Jira with its Jira key",
)
def publish_story(backlog_id: str, epic_record_id: str, story_record_id: str, body: PublishRequest):
    try:
        updated = backlog_service.publish_story(story_record_id, body.jira_key)
    except FileNotFoundError as err:
        raise HTTPException(status_code=404, detail=str(err)) from err
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    return updated


@router.post(
    "/{backlog_id}/epics/{epic_record_id}/stories",
    summary="Save generated stories for an epic",
    status_code=201,
)
def save_stories(backlog_id: str, epic_record_id: str, payload: StoriesWrapper):
    from backlog_generation.epic_agent import JiraStoryOutput
    story_outputs = [
        JiraStoryOutput(
            story_id=s.story_id,
            epic_id=s.epic_id,
            title=s.title,
            summary=s.summary,
            description=s.description,
            acceptance_criteria=s.acceptance_criteria,
            priority=s.priority,
            status=s.status,
        )
        for s in payload.stories
    ]
    try:
        saved = backlog_service.persist_saved_stories(epic_record_id, story_outputs)
    except FileNotFoundError as err:
        raise HTTPException(status_code=404, detail=str(err)) from err
    return saved


@router.patch(
    "/{backlog_id}/epics/{epic_record_id}/status",
    summary="Transition epic status (draft→pending_approval→approved|rejected→synced_to_jira)",
)
def update_epic_status(backlog_id: str, epic_record_id: str, body: StatusUpdate):
    try:
        updated = backlog_service.set_epic_status(
            epic_record_id,
            body.status,
            reviewed_by=body.reviewed_by,
            review_comment=body.review_comment,
            submitted_by=body.submitted_by,
        )
    except FileNotFoundError as err:
        raise HTTPException(status_code=404, detail=str(err)) from err
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    return updated


@router.patch(
    "/{backlog_id}/epics/{epic_record_id}/stories/{story_record_id}/status",
    summary="Transition story status",
)
def update_story_status(
    backlog_id: str, epic_record_id: str, story_record_id: str, body: StatusUpdate
):
    try:
        updated = backlog_service.set_story_status(
            story_record_id,
            body.status,
            reviewed_by=body.reviewed_by,
            review_comment=body.review_comment,
            submitted_by=body.submitted_by,
        )
    except FileNotFoundError as err:
        raise HTTPException(status_code=404, detail=str(err)) from err
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    return updated


@router.get("/approvals/events", summary="Get approval event history (cross-module audit log)")
def list_approval_events(
    artifact_type: Optional[str] = Query(
        None, description="Filter by artifact type: epic, story, requirement, …"
    ),
    artifact_id: Optional[str] = Query(
        None, description="Filter by specific artifact record ID"
    ),
    limit: int = Query(200, ge=1, le=1000),
):
    return backlog_service.get_approval_events(
        artifact_type=artifact_type,
        artifact_id=artifact_id,
        limit=limit,
    )
