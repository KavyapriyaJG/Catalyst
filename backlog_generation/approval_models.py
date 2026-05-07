"""SQLAlchemy ORM model for the shared cross-module approval audit log."""

from datetime import datetime

from sqlalchemy import Text, VARCHAR
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func, text
from sqlalchemy import TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID

from backlog_generation.models import Base


class ApprovalEvent(Base):
    """Immutable audit record written on every approve/reject action.

    Module-agnostic: every artifact type (epic, story, prd, srs,
    test_case, deployment_plan, …) appends a row here.  The ActivityLog UI
    reads this table to show the reviewer their full history queue.
    """

    __tablename__ = "approval_events"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    # ── What artifact was acted on ──────────────────────────────────────────
    artifact_type: Mapped[str] = mapped_column(
        VARCHAR(32), nullable=False, index=True
    )
    # "epic" | "story" | "prd" | "srs" | "design" |
    # "test_case" | "test_suite" | "deployment_plan" | ...

    artifact_id: Mapped[str] = mapped_column(
        VARCHAR(255), nullable=False, index=True
    )
    # UUID string for DB-backed artifacts; filename for file-backed ones (PRD)

    artifact_name: Mapped[str] = mapped_column(Text, nullable=False)
    # Human-readable label shown in ActivityLog (epic_name, prd title, etc.)

    # ── Transition ──────────────────────────────────────────────────────────
    from_status: Mapped[str] = mapped_column(VARCHAR(32), nullable=False)
    to_status: Mapped[str] = mapped_column(VARCHAR(32), nullable=False)
    # "approved" | "rejected" | "pending_approval" | "synced_to_jira" …

    # ── People ──────────────────────────────────────────────────────────────
    submitted_by: Mapped[str | None] = mapped_column(VARCHAR(255), nullable=True)
    # Who originally submitted the artifact for review.

    reviewed_by: Mapped[str | None] = mapped_column(VARCHAR(255), nullable=True)
    # Who performed this approve/reject action.
    # Populated from request body now; from JWT/session when auth is added.

    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Reviewer's comment — required for rejections, optional for approvals.

    # ── Timestamp ───────────────────────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
