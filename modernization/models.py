"""SQLAlchemy ORM models for modernization documents."""

from datetime import datetime

from sqlalchemy import ForeignKey, Text, VARCHAR, ARRAY
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func, text
from sqlalchemy import TIMESTAMP

from backlog_generation.models import Base


class ModernizationDocRecord(Base):
    """Represents one modernization document with linked PRDs and supporting docs."""

    __tablename__ = "modernization_docs"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        VARCHAR(32), nullable=False, server_default="draft"
    )

    modernization_goals: Mapped[str | None] = mapped_column(Text, nullable=True)

    linked_prds: Mapped[list] = mapped_column(
        ARRAY(Text), nullable=False, server_default=text("'{}'::text[]")
    )

    source_assets: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )

    generated_sections: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )

    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    submitted_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )

    submitted_by: Mapped[str | None] = mapped_column(VARCHAR(255), nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(VARCHAR(255), nullable=True)
    review_comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    approval_events: Mapped[list["ApprovalEvent"]] = relationship(
        "ApprovalEvent",
        foreign_keys="ApprovalEvent.artifact_id",
        viewonly=True,
        lazy="select",
        primaryjoin="and_(foreign(ApprovalEvent.artifact_id) == ModernizationDocRecord.id, ApprovalEvent.artifact_type == 'modernization')"
    )
