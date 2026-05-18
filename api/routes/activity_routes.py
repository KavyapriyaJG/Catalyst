"""REST endpoints for activity log and persisted submissions."""

from fastapi import APIRouter, HTTPException

from api.routes.backlog_routes import StatusUpdate
from api.services import backlog_service
from api.services import activity_service
from api.services import prd_service
from api.services import modernization_service

router = APIRouter(prefix="/activity", tags=["activity"])


@router.get("/submissions", summary="Get all persisted submissions from approval events")
def list_submissions():
    """Load all persisted submissions (awaiting/approved/rejected) from approval_events table."""
    return activity_service.get_all_submissions()


@router.get("/planning", summary="Get planning activity events")
def list_planning_activities():
    """Get all planning-related activities (SRS/specification events)."""
    return activity_service.get_planning_activities()


@router.patch(
    "/approvals/{artifact_type}/{artifact_id}/status",
    summary="Generic artifact status transition by artifact type and single artifact id",
)
def update_artifact_status(artifact_type: str, artifact_id: str, body: StatusUpdate):
    """Update status for any supported artifact type using a single artifact id.

    Supported artifact types: epic, story, prd, modernization.
    """
    normalized_type = artifact_type.strip().lower()
    try:
        if normalized_type == "epic":
            return backlog_service.set_epic_status(
                artifact_id,
                body.status,
                reviewed_by=body.reviewed_by,
                review_comment=body.review_comment,
                submitted_by=body.submitted_by,
            )
        if normalized_type == "story":
            return backlog_service.set_story_status(
                artifact_id,
                body.status,
                reviewed_by=body.reviewed_by,
                review_comment=body.review_comment,
                submitted_by=body.submitted_by,
            )
        if normalized_type == "prd":
            return prd_service.set_prd_status(
                artifact_id,
                body.status,
                reviewed_by=body.reviewed_by,
                review_comment=body.review_comment,
            )
        if normalized_type == "modernization":
            action = "approve" if body.status == "approved" else "reject"
            return modernization_service.review_modernization_doc(
                artifact_id,
                action=action,
                reviewed_by=body.reviewed_by or "Unknown",
                comment=body.review_comment or "",
            )
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported artifact_type {artifact_type!r}. "
                "Supported types: epic, story, prd, modernization."
            ),
        )
    except FileNotFoundError as err:
        raise HTTPException(status_code=404, detail=str(err)) from err
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err

