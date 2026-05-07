"""High-level service wrapping backlog repository + session lifecycle."""

from __future__ import annotations

import shutil
from pathlib import Path

from backlog_generation.backlog_models import (
    BacklogRecord,
    GeneratedEpicRecord,
    GeneratedStoryRecord,
)
from backlog_generation.backlog_repository import (
    create_backlog,
    delete_backlog,
    get_backlog_with_epics,
    get_epic_with_stories,
    get_story,
    list_backlogs,
    mark_epic_published,
    mark_story_published,
    save_epics,
    save_stories,
    update_epic_status,
    update_story_status,
)
from backlog_generation.approval_models import ApprovalEvent
from backlog_generation.db import get_session
from backlog_generation.epic_agent import JiraEpicOutput, JiraStoryOutput
from config import get_settings


def _story_to_dict(story: GeneratedStoryRecord) -> dict:
    return {
        "record_id": str(story.id),
        "story_id": story.story_id,
        "title": story.title,
        "summary": story.summary,
        "description": story.description,
        "priority": story.priority,
        "acceptance_criteria": story.acceptance_criteria,
        "status": story.status,
        "jira_key": story.jira_key,
        "reviewed_by": story.reviewed_by,
        "review_comment": story.review_comment,
        "reviewed_at": story.reviewed_at.isoformat() if story.reviewed_at else None,
        "created_at": story.created_at.isoformat(),
        "updated_at": story.updated_at.isoformat(),
    }


def _epic_to_dict(epic: GeneratedEpicRecord, include_stories: bool = True) -> dict:
    d = {
        "record_id": str(epic.id),
        "epic_id": epic.epic_id,
        "epic_name": epic.epic_name,
        "epic_summary": epic.epic_summary,
        "business_value": epic.business_value,
        "scope": epic.scope,
        "out_of_scope": epic.out_of_scope,
        "assumptions": epic.assumptions,
        "acceptance_criteria": epic.acceptance_criteria,
        "risks_and_dependencies": epic.risks_and_dependencies,
        "status": epic.status,
        "jira_key": epic.jira_key,
        "reviewed_by": epic.reviewed_by,
        "review_comment": epic.review_comment,
        "reviewed_at": epic.reviewed_at.isoformat() if epic.reviewed_at else None,
        "created_at": epic.created_at.isoformat(),
        "updated_at": epic.updated_at.isoformat(),
    }
    if include_stories:
        d["stories"] = [_story_to_dict(s) for s in epic.stories]
    return d


def _backlog_to_dict(backlog: BacklogRecord, include_epics: bool = True) -> dict:
    d = {
        "id": str(backlog.id),
        "prompt": backlog.prompt,
        "status": backlog.status,
        "source_files": backlog.source_files,
        "created_at": backlog.created_at.isoformat(),
    }
    if include_epics:
        d["epics"] = [_epic_to_dict(e) for e in backlog.epics]
    return d


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def create_and_save_epics(
    prompt: str,
    epics: list[JiraEpicOutput],
    source_files: list[str],
    backlog_id: str | None = None,
) -> dict:
    """Persist backlog + epics; returns the full backlog dict with record IDs."""
    with get_session() as session:
        if backlog_id:
            backlog = create_backlog(session, prompt, source_files)
            # Override the server-generated UUID with the one we pre-allocated for
            # the filesystem directory. We do this by flushing, then updating.
            # SQLAlchemy won't let us set a server_default PK directly after flush,
            # so instead we use a regular insert with the provided id.
            #
            # Simpler: just ignore backlog_id param and always use server-generated id,
            # then rename the directory afterward. Return the real UUID.
            real_id = str(backlog.id)
        else:
            backlog = create_backlog(session, prompt, source_files)
            real_id = str(backlog.id)

        save_epics(session, real_id, epics)
        # Need to reload with epics for response
        from sqlalchemy.orm import selectinload
        from sqlalchemy import select
        full = session.scalar(
            select(BacklogRecord)
            .options(selectinload(BacklogRecord.epics))
            .where(BacklogRecord.id == real_id)
        )
        result = _backlog_to_dict(full, include_epics=True)
        # Strip stories key since no stories exist yet
        for e in result["epics"]:
            e.pop("stories", None)
    return result


def get_all_backlogs() -> list[dict]:
    with get_session() as session:
        return list_backlogs(session)


def get_backlog(backlog_id: str) -> dict | None:
    with get_session() as session:
        backlog = get_backlog_with_epics(session, backlog_id)
        if backlog is None:
            return None
        return _backlog_to_dict(backlog)


def get_epic(epic_record_id: str) -> dict | None:
    with get_session() as session:
        epic = get_epic_with_stories(session, epic_record_id)
        if epic is None:
            return None
        return _epic_to_dict(epic, include_stories=True)


def get_story_by_id(story_record_id: str) -> dict | None:
    with get_session() as session:
        story = get_story(session, story_record_id)
        if story is None:
            return None
        return _story_to_dict(story)


def remove_backlog(backlog_id: str) -> bool:
    """Delete DB records and associated files. Returns False if not found."""
    settings = get_settings()
    with get_session() as session:
        found = delete_backlog(session, backlog_id)

    if not found:
        return False

    # Clean up filesystem (best-effort)
    backlog_dir: Path = settings.BACKLOG_FILES_DIR / backlog_id
    if backlog_dir.exists():
        shutil.rmtree(backlog_dir, ignore_errors=True)

    return True


def set_epic_status(
    epic_record_id: str,
    new_status: str,
    reviewed_by: str | None = None,
    review_comment: str | None = None,
    submitted_by: str | None = None,
) -> dict:
    """Update epic status; propagates ValueError / FileNotFoundError."""
    with get_session() as session:
        rec = update_epic_status(
            session, epic_record_id, new_status,
            reviewed_by=reviewed_by,
            review_comment=review_comment,
            submitted_by=submitted_by,
        )
        return _epic_to_dict(rec, include_stories=False)


def set_story_status(
    story_record_id: str,
    new_status: str,
    reviewed_by: str | None = None,
    review_comment: str | None = None,
    submitted_by: str | None = None,
) -> dict:
    """Update story status; propagates ValueError / FileNotFoundError."""
    with get_session() as session:
        rec = update_story_status(
            session, story_record_id, new_status,
            reviewed_by=reviewed_by,
            review_comment=review_comment,
            submitted_by=submitted_by,
        )
        return _story_to_dict(rec)


def persist_saved_stories(epic_record_id: str, stories: list[JiraStoryOutput]) -> list[dict]:
    """Persist generated stories for a given epic record."""
    with get_session() as session:
        if session.get(GeneratedEpicRecord, epic_record_id) is None:
            raise FileNotFoundError(f"Epic record {epic_record_id!r} not found.")
        records = save_stories(session, epic_record_id, stories)
        return [_story_to_dict(r) for r in records]


def publish_epic(epic_record_id: str, jira_key: str) -> dict:
    """Mark epic as synced_to_jira with the given Jira key."""
    with get_session() as session:
        rec = mark_epic_published(session, epic_record_id, jira_key)
        return _epic_to_dict(rec, include_stories=False)


def publish_story(story_record_id: str, jira_key: str) -> dict:
    """Mark story as synced_to_jira with the given Jira key."""
    with get_session() as session:
        rec = mark_story_published(session, story_record_id, jira_key)
        return _story_to_dict(rec)


def get_approval_events(
    artifact_type: str | None = None,
    artifact_id: str | None = None,
    limit: int = 200,
) -> list[dict]:
    """Return approval_events rows, optionally filtered by artifact type/id."""
    from sqlalchemy import select

    with get_session() as session:
        stmt = select(ApprovalEvent).order_by(ApprovalEvent.created_at.desc())
        if artifact_type:
            stmt = stmt.where(ApprovalEvent.artifact_type == artifact_type)
        if artifact_id:
            stmt = stmt.where(ApprovalEvent.artifact_id == artifact_id)
        stmt = stmt.limit(limit)
        rows = session.scalars(stmt).all()
        return [
            {
                "id": row.id,
                "artifact_type": row.artifact_type,
                "artifact_id": row.artifact_id,
                "artifact_name": row.artifact_name,
                "from_status": row.from_status,
                "to_status": row.to_status,
                "submitted_by": row.submitted_by,
                "reviewed_by": row.reviewed_by,
                "comment": row.comment,
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ]
