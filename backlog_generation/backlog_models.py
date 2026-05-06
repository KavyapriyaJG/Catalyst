"""SQLAlchemy ORM models for generated backlogs, epics, and stories."""

from datetime import datetime

from sqlalchemy import ForeignKey, Text, VARCHAR
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func, text
from sqlalchemy import TIMESTAMP

from backlog_generation.models import Base


class BacklogRecord(Base):
    """Represents one backlog generation run."""

    __tablename__ = "backlogs"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        VARCHAR(32), nullable=False, server_default="generated"
    )
    source_files: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )

    epics: Mapped[list["GeneratedEpicRecord"]] = relationship(
        "GeneratedEpicRecord",
        back_populates="backlog",
        cascade="all, delete-orphan",
        lazy="select",
    )


class GeneratedEpicRecord(Base):
    """An LLM-generated epic belonging to one backlog."""

    __tablename__ = "generated_epics"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    backlog_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("backlogs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    epic_id: Mapped[str] = mapped_column(Text, nullable=False)
    epic_name: Mapped[str] = mapped_column(Text, nullable=False)
    epic_summary: Mapped[str] = mapped_column(Text, nullable=False)
    business_value: Mapped[str] = mapped_column(Text, nullable=False)
    scope: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    out_of_scope: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    assumptions: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    acceptance_criteria: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    risks_and_dependencies: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    status: Mapped[str] = mapped_column(
        VARCHAR(32), nullable=False, server_default="draft"
    )
    jira_key: Mapped[str | None] = mapped_column(VARCHAR(128), nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    backlog: Mapped["BacklogRecord"] = relationship(
        "BacklogRecord", back_populates="epics"
    )
    stories: Mapped[list["GeneratedStoryRecord"]] = relationship(
        "GeneratedStoryRecord",
        back_populates="epic",
        cascade="all, delete-orphan",
        lazy="select",
    )


class GeneratedStoryRecord(Base):
    """An LLM-generated story belonging to one epic."""

    __tablename__ = "generated_stories"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    epic_record_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("generated_epics.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    story_id: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[str] = mapped_column(Text, nullable=False)
    acceptance_criteria: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    status: Mapped[str] = mapped_column(
        VARCHAR(32), nullable=False, server_default="draft"
    )
    jira_key: Mapped[str | None] = mapped_column(VARCHAR(128), nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    epic: Mapped["GeneratedEpicRecord"] = relationship(
        "GeneratedEpicRecord", back_populates="stories"
    )
