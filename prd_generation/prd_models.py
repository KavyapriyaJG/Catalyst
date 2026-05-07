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
