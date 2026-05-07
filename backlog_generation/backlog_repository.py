"""Data-access layer for backlogs, epics, and stories.

All functions take an explicit ``Session`` so callers control the transaction
boundary via :func:`backlog_generation.db.get_session`.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from approval.models import ApprovalEvent
from backlog_generation.backlog_models import (
    BacklogRecord,
    GeneratedEpicRecord,
    GeneratedStoryRecord,
)
from backlog_generation.epic_agent import JiraEpicOutput, JiraStoryOutput

# ---------------------------------------------------------------------------
# Valid status transitions (server-side enforcement)
# ---------------------------------------------------------------------------
_EPIC_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"pending_approval"},
    "pending_approval": {"approved", "rejected"},
    "approved": {"synced_to_jira"},
    "rejected": set(),
    "synced_to_jira": set(),
}

_STORY_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"pending_approval"},
    "pending_approval": {"approved", "rejected"},
    "approved": {"synced_to_jira"},
    "rejected": set(),
    "synced_to_jira": set(),
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _write_approval_event(
    session: Session,
    *,
    artifact_type: str,
    artifact_id: str,
    artifact_name: str,
    from_status: str,
    to_status: str,
    reviewed_by: str | None,
    comment: str | None,
    submitted_by: str | None = None,
) -> None:
    """Append one row to approval_events (best-effort — never raises)."""
    try:
        event = ApprovalEvent(
            artifact_type=artifact_type,
            artifact_id=artifact_id,
            artifact_name=artifact_name,
            from_status=from_status,
            to_status=to_status,
            submitted_by=submitted_by,
            reviewed_by=reviewed_by,
            comment=comment,
        )
        session.add(event)
    except Exception:
        pass  # audit writes must not break the primary status transition


# ---------------------------------------------------------------------------
# Backlog CRUD
# ---------------------------------------------------------------------------

def create_backlog(
    session: Session,
    prompt: str,
    source_files: list[str],
) -> BacklogRecord:
    """Persist a new :class:`BacklogRecord` and flush to obtain the PK."""
    record = BacklogRecord(prompt=prompt, source_files=source_files, status="generated")
    session.add(record)
    session.flush()  # populate server-generated `id`
    return record


def list_backlogs(session: Session) -> list[dict]:
    """Return a lightweight list suitable for the backlog index UI."""
    rows = session.execute(
        select(
            BacklogRecord.id,
            BacklogRecord.prompt,
            BacklogRecord.status,
            BacklogRecord.created_at,
            func.count(GeneratedEpicRecord.id).label("epic_count"),
        )
        .outerjoin(GeneratedEpicRecord, GeneratedEpicRecord.backlog_id == BacklogRecord.id)
        .group_by(BacklogRecord.id)
        .order_by(BacklogRecord.created_at.desc())
    ).all()

    return [
        {
            "id": str(r.id),
            "prompt": r.prompt,
            "status": r.status,
            "epic_count": r.epic_count,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]


def get_backlog_with_epics(
    session: Session, backlog_id: str
) -> BacklogRecord | None:
    """Load a backlog and eagerly fetch its epics + stories."""
    return session.scalar(
        select(BacklogRecord)
        .options(
            selectinload(BacklogRecord.epics).selectinload(GeneratedEpicRecord.stories)
        )
        .where(BacklogRecord.id == backlog_id)
    )


def get_epic_with_stories(session: Session, epic_record_id: str) -> GeneratedEpicRecord | None:
    """Load a single epic and eagerly fetch its stories."""
    from sqlalchemy.orm import selectinload as _sel
    return session.scalar(
        select(GeneratedEpicRecord)
        .options(_sel(GeneratedEpicRecord.stories))
        .where(GeneratedEpicRecord.id == epic_record_id)
    )


def get_story(session: Session, story_record_id: str) -> GeneratedStoryRecord | None:
    """Load a single story by its record UUID."""
    return session.get(GeneratedStoryRecord, story_record_id)


def delete_backlog(session: Session, backlog_id: str) -> bool:
    """Delete a backlog and all related records (cascade). Returns True if found."""
    record = session.get(BacklogRecord, backlog_id)
    if record is None:
        return False
    session.delete(record)
    return True


# ---------------------------------------------------------------------------
# Epic persistence
# ---------------------------------------------------------------------------

def save_epics(
    session: Session,
    backlog_id: str,
    epics: list[JiraEpicOutput],
) -> list[GeneratedEpicRecord]:
    """Bulk-insert epics for a backlog. Returns the persisted records."""
    records: list[GeneratedEpicRecord] = []
    for epic in epics:
        rec = GeneratedEpicRecord(
            backlog_id=backlog_id,
            epic_id=epic.epic_id,
            epic_name=epic.epic_name,
            epic_summary=epic.epic_summary,
            business_value=epic.business_value,
            scope=epic.scope,
            out_of_scope=epic.out_of_scope,
            assumptions=epic.assumptions,
            acceptance_criteria=epic.acceptance_criteria,
            risks_and_dependencies=epic.risks_and_dependencies,
            status="draft",
        )
        session.add(rec)
        records.append(rec)
    session.flush()
    return records


def update_epic_status(
    session: Session,
    epic_record_id: str,
    new_status: str,
    reviewed_by: str | None = None,
    review_comment: str | None = None,
    submitted_by: str | None = None,
) -> GeneratedEpicRecord:
    """Transition an epic to a new status, raising ValueError for invalid moves."""
    record = session.get(GeneratedEpicRecord, epic_record_id)
    if record is None:
        raise FileNotFoundError(f"Epic record {epic_record_id!r} not found.")
    allowed = _EPIC_TRANSITIONS.get(record.status, set())
    if new_status not in allowed:
        raise ValueError(
            f"Cannot transition epic from {record.status!r} to {new_status!r}. "
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
    _write_approval_event(
        session,
        artifact_type="epic",
        artifact_id=epic_record_id,
        artifact_name=record.epic_name,
        from_status=from_status,
        to_status=new_status,
        reviewed_by=reviewed_by,
        comment=review_comment,
        submitted_by=submitted_by,
    )
    session.flush()
    return record


def mark_epic_published(
    session: Session,
    epic_record_id: str,
    jira_key: str,
) -> GeneratedEpicRecord:
    """Set jira_key and status='synced_to_jira' for a published epic."""
    record = session.get(GeneratedEpicRecord, epic_record_id)
    if record is None:
        raise FileNotFoundError(f"Epic record {epic_record_id!r} not found.")
    record.jira_key = jira_key
    record.status = "synced_to_jira"
    session.flush()
    return record


# ---------------------------------------------------------------------------
# Story persistence
# ---------------------------------------------------------------------------

def save_stories(
    session: Session,
    epic_record_id: str,
    stories: list[JiraStoryOutput],
) -> list[GeneratedStoryRecord]:
    """Bulk-insert stories for an epic. Returns the persisted records."""
    records: list[GeneratedStoryRecord] = []
    for story in stories:
        rec = GeneratedStoryRecord(
            epic_record_id=epic_record_id,
            story_id=story.story_id,
            title=story.title,
            summary=story.summary,
            description=story.description,
            priority=story.priority,
            acceptance_criteria=story.acceptance_criteria,
            status=getattr(story, "status", "draft") or "draft",
        )
        session.add(rec)
        records.append(rec)
    session.flush()
    return records


def update_story_status(
    session: Session,
    story_record_id: str,
    new_status: str,
    reviewed_by: str | None = None,
    review_comment: str | None = None,
    submitted_by: str | None = None,
) -> GeneratedStoryRecord:
    """Transition a story to a new status, raising ValueError for invalid moves."""
    record = session.get(GeneratedStoryRecord, story_record_id)
    if record is None:
        raise FileNotFoundError(f"Story record {story_record_id!r} not found.")
    allowed = _STORY_TRANSITIONS.get(record.status, set())
    if new_status not in allowed:
        raise ValueError(
            f"Cannot transition story from {record.status!r} to {new_status!r}. "
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
    _write_approval_event(
        session,
        artifact_type="story",
        artifact_id=story_record_id,
        artifact_name=record.title,
        from_status=from_status,
        to_status=new_status,
        reviewed_by=reviewed_by,
        comment=review_comment,
        submitted_by=submitted_by,
    )
    session.flush()
    return record


def mark_story_published(
    session: Session,
    story_record_id: str,
    jira_key: str,
) -> GeneratedStoryRecord:
    """Set jira_key and status='synced_to_jira' for a published story."""
    record = session.get(GeneratedStoryRecord, story_record_id)
    if record is None:
        raise FileNotFoundError(f"Story record {story_record_id!r} not found.")
    record.jira_key = jira_key
    record.status = "synced_to_jira"
    session.flush()
    return record
