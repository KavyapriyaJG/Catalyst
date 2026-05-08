"""Get all persisted submissions from approval_events across artifact types."""

from __future__ import annotations

import random

from sqlalchemy import select

from approval.models import ApprovalEvent
from backlog_generation.db import get_session


def get_activity_submissions() -> list[dict]:
    """Get all persisted submissions from approval_events table.
    
    Fetches approval events for all artifact types (epic, story, prd, etc.),
    groups by artifact_id, and returns the latest status for each.
    Returns Submission-compatible dicts for awaiting/approved/rejected artifacts.
    """
    with get_session() as session:
        # Get all approval events ordered by artifact_id and recency
        stmt = select(ApprovalEvent).order_by(
            ApprovalEvent.artifact_id,
            ApprovalEvent.created_at.desc(),
        )
        rows = session.scalars(stmt).all()

        # Group by artifact_id, keep only latest event per artifact
        latest_events: dict[str, ApprovalEvent] = {}
        for row in rows:
            if row.artifact_id not in latest_events:
                latest_events[row.artifact_id] = row

        submissions = []
        for artifact_id, event in latest_events.items():
            # Only include awaiting/approved/rejected statuses
            if event.to_status not in {"awaiting", "approved", "rejected", "pending_approval"}:
                continue

            # Map pending_approval to awaiting for UI
            status = "awaiting" if event.to_status == "pending_approval" else event.to_status

            # Generate random AI Risk score (20-85 range)
            ai_risk = random.randint(20, 85)

            submission = {
                "id": event.artifact_id,
                "name": event.artifact_name,
                "submitter": event.submitted_by or "Catalyst Agent",
                "date": event.created_at.isoformat(),
                "type": event.artifact_type,
                "status": status,
                "reviewComment": event.comment,
                "reviewedAt": event.created_at.isoformat() if status in {"approved", "rejected"} else None,
                "reviewed_by": event.reviewed_by,
                "aiRisk": ai_risk,
            }

            submissions.append(submission)

        return submissions
