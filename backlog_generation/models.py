from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class IssueRecord(Base):
    __tablename__ = "issues"

    id: Mapped[int] = mapped_column(primary_key=True)
    issue_key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)


class IssueHierarchyRecord(Base):
    __tablename__ = "issue_hierarchy"

    parent_id: Mapped[int] = mapped_column(ForeignKey("issues.id", ondelete="CASCADE"), primary_key=True)
    child_id: Mapped[int] = mapped_column(ForeignKey("issues.id", ondelete="CASCADE"), primary_key=True)


class IssueLinkRecord(Base):
    __tablename__ = "issue_links"

    source_id: Mapped[int] = mapped_column(ForeignKey("issues.id", ondelete="CASCADE"), primary_key=True)
    target_id: Mapped[int] = mapped_column(ForeignKey("issues.id", ondelete="CASCADE"), primary_key=True)
    link_type: Mapped[str] = mapped_column(String(128), primary_key=True)
