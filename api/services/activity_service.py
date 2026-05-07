"""Service layer for activity/approval submissions across all artifact types."""

from sqlalchemy import select

from approval.models import ApprovalEvent
from approval.submissions import get_activity_submissions
from backlog_generation.db import get_session


def get_all_submissions() -> list[dict]:
    """Fetch all persisted submissions from approval_events table."""
    return get_activity_submissions()


def get_planning_activities() -> list[dict]:
    """Fetch planning activities (SRS/specification events).
    
    Returns activities from the approval_events table filtered for planning artifacts.
    """
    with get_session() as session:
        # Query for PRD artifacts only
        stmt = select(ApprovalEvent).where(
            ApprovalEvent.artifact_type == "prd"
        ).order_by(ApprovalEvent.created_at.desc())
        
        events = session.scalars(stmt).all()
        
        return [
            {
                "id": str(e.id),
                "action": _map_action_type(e.to_status),
                "artifact": e.artifact_name,
                "user": e.reviewed_by or e.submitted_by or "System",
                "timestamp": e.created_at.isoformat(),
                "type": _map_event_type(e.to_status),
            }
            for e in events
        ]


def _map_action_type(status: str) -> str:
    """Map status to human-readable action."""
    mapping = {
        "draft": "Planning document created",
        "pending_approval": "Document submitted for review",
        "approved": "Planning document approved",
        "rejected": "Planning document rejected",
        "synced": "Document synced to system",
    }
    return mapping.get(status, f"Planning {status}")


def _map_event_type(status: str) -> str:
    """Map status to event type."""
    if status == "approved":
        return "approved"
    elif status == "rejected":
        return "rejected"
    elif status == "pending_approval":
        return "submitted"
    elif status == "draft":
        return "created"
    else:
        return "generated"

