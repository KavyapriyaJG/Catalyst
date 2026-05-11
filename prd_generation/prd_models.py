"""SQLAlchemy ORM models for generated PRDs."""

from datetime import datetime

from sqlalchemy import ForeignKey, Text, VARCHAR
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func, text
from sqlalchemy import TIMESTAMP

from backlog_generation.models import Base


class GeneratedPRDRecord(Base):
    """Represents one PRD generation run."""

    __tablename__ = "generated_prds"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    prd_name: Mapped[str] = mapped_column(
        VARCHAR(255), nullable=False, server_default="Untitled PRD"
    )
    source_files: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    status: Mapped[str] = mapped_column(
        VARCHAR(32), nullable=False, server_default="draft"
    )
    
    # Full PRD stored as JSON - single source of truth
    prd_content: Mapped[dict] = mapped_column(
        JSONB, nullable=True, server_default=text("'{}'::jsonb")
    )
    
    # Review metadata (latest state cached for performance)
    reviewed_by: Mapped[str | None] = mapped_column(VARCHAR(255), nullable=True)
    review_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    
    # Audit
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    comments: Mapped[list["PRDComment"]] = relationship(
        "PRDComment", back_populates="prd", cascade="all, delete-orphan"
    )


class PRDComment(Base):
    """An inline comment (or reply) on a specific section of a PRD."""

    __tablename__ = "prd_comments"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    prd_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("generated_prds.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    section_id: Mapped[str] = mapped_column(VARCHAR(255), nullable=False)
    section_title: Mapped[str] = mapped_column(Text, nullable=False)
    author: Mapped[str] = mapped_column(VARCHAR(255), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    highlighted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    parent_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("prd_comments.id", ondelete="CASCADE"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )

    prd: Mapped["GeneratedPRDRecord"] = relationship(
        "GeneratedPRDRecord", back_populates="comments"
    )
    replies: Mapped[list["PRDComment"]] = relationship(
        "PRDComment",
        back_populates="parent",
        cascade="all",
        passive_deletes=True,
    )
    parent: Mapped["PRDComment | None"] = relationship(
        "PRDComment",
        back_populates="replies",
        remote_side="PRDComment.id",
    )
