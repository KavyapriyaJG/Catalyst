"""Data-access layer for generated PRDs.

All functions take an explicit ``Session`` so callers control the transaction
boundary via :func:`backlog_generation.db.get_session`.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from prd_generation.prd_models import GeneratedPRDRecord
from approval.models import ApprovalEvent

# ---------------------------------------------------------------------------
# Valid status transitions for PRDs
# ---------------------------------------------------------------------------
_PRD_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"pending_approval"},
    "pending_approval": {"approved", "rejected"},
    "approved": {"rejected", "pending_approval"},
    "rejected": {"approved", "pending_approval", "draft"},
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _write_prd_approval_event(
    session: Session,
    *,
    prd_id: str,
    prd_name: str,
    from_status: str,
    to_status: str,
    reviewed_by: str | None,
    comment: str | None,
    submitted_by: str | None = None,
) -> None:
    """Append one row to shared approval_events table (best-effort — never raises)."""
    try:
        event = ApprovalEvent(
            artifact_type="prd",
            artifact_id=prd_id,
            artifact_name=prd_name,
            from_status=from_status,
            to_status=to_status,
            submitted_by=submitted_by,
            reviewed_by=reviewed_by,
            comment=comment,
            backlog_id=None,  # PRDs do not belong to backlogs
        )
        session.add(event)
    except Exception:
        pass  # audit writes must not break the primary status transition


# ---------------------------------------------------------------------------
# PRD CRUD operations
# ---------------------------------------------------------------------------

def create_prd(
    session: Session,
    source_files: list[str],
    prd_content: dict[str, Any] | None = None,
) -> GeneratedPRDRecord:
    """Create and persist a new PRD record."""
    record = GeneratedPRDRecord(
        source_files=source_files,
        status="draft",
        prd_content=prd_content or {},
    )
    session.add(record)
    session.flush()
    return record


def list_prds(session: Session) -> list[dict]:
    """Return a lightweight list of all PRDs for index/listing UI."""
    rows = session.execute(
        select(
            GeneratedPRDRecord.id,
            GeneratedPRDRecord.status,
            GeneratedPRDRecord.created_at,
            GeneratedPRDRecord.updated_at,
        )
        .order_by(GeneratedPRDRecord.created_at.desc())
    ).all()

    return [
        {
            "id": str(r.id),
            "status": r.status,
            "created_at": r.created_at.isoformat(),
            "updated_at": r.updated_at.isoformat(),
        }
        for r in rows
    ]


def get_prd(session: Session, prd_id: str) -> GeneratedPRDRecord | None:
    """Load a single PRD by ID."""
    return session.get(GeneratedPRDRecord, prd_id)


def update_prd_content(
    session: Session,
    prd_id: str,
    prd_content: dict[str, Any],
) -> GeneratedPRDRecord:
    """Update PRD content."""
    record = session.get(GeneratedPRDRecord, prd_id)
    if record is None:
        raise FileNotFoundError(f"PRD record {prd_id!r} not found.")
    
    record.prd_content = prd_content
    session.flush()
    return record


def update_prd_status(
    session: Session,
    prd_id: str,
    new_status: str,
    reviewed_by: str | None = None,
    review_comment: str | None = None,
) -> GeneratedPRDRecord:
    """Transition a PRD to a new status with validation."""
    record = session.get(GeneratedPRDRecord, prd_id)
    if record is None:
        raise FileNotFoundError(f"PRD record {prd_id!r} not found.")
    
    allowed = _PRD_TRANSITIONS.get(record.status, set())
    if new_status not in allowed:
        raise ValueError(
            f"Cannot transition PRD from {record.status!r} to {new_status!r}. "
            f"Allowed: {sorted(allowed) or 'none'}."
        )
    
    from_status = record.status
    record.status = new_status
    
    if reviewed_by is not None:
        record.reviewed_by = reviewed_by
    if review_comment is not None:
        record.review_comment = review_comment
    
    if new_status in {"approved", "rejected"}:
        record.reviewed_at = datetime.now(timezone.utc)
    
    # Generate PRD filename for display
    prd_filename = f"prd_{record.created_at.strftime('%Y%m%d_%H%M%S')}" if record.created_at else f"prd_{prd_id}"
    
    _write_prd_approval_event(
        session,
        prd_id=prd_id,
        prd_name=prd_filename,
        from_status=from_status,
        to_status=new_status,
        reviewed_by=reviewed_by,
        comment=review_comment,
    )
    
    session.flush()
    return record


def delete_prd(session: Session, prd_id: str) -> bool:
    """Delete a PRD and all related records. Returns True if found."""
    record = session.get(GeneratedPRDRecord, prd_id)
    if record is None:
        return False
    session.delete(record)
    return True


def get_prd_approval_history(
    session: Session, prd_id: str
) -> list[dict]:
    """Get approval event history for a PRD from shared approval_events table."""
    events = session.execute(
        select(ApprovalEvent)
        .where(ApprovalEvent.artifact_id == prd_id)
        .where(ApprovalEvent.artifact_type == "prd")
        .order_by(ApprovalEvent.created_at.asc())
    ).scalars().all()

    return [
        {
            "id": str(e.id),
            "artifact_type": e.artifact_type,
            "artifact_name": e.artifact_name,
            "from_status": e.from_status,
            "to_status": e.to_status,
            "submitted_by": e.submitted_by,
            "reviewed_by": e.reviewed_by,
            "comment": e.comment,
            "created_at": e.created_at.isoformat(),
        }
        for e in events
    ]
