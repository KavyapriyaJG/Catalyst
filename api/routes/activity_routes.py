"""REST endpoints for activity log and persisted submissions."""

from fastapi import APIRouter

from api.services import activity_service

router = APIRouter(prefix="/activity", tags=["activity"])


@router.get("/submissions", summary="Get all persisted submissions from approval events")
def list_submissions():
    """Load all persisted submissions (awaiting/approved/rejected) from approval_events table."""
    return activity_service.get_all_submissions()
