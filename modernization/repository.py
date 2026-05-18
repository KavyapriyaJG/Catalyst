"""Repository layer for modernization document operations."""

from typing import Optional
from sqlalchemy.orm import Session

from modernization.models import ModernizationDocRecord


class ModernizationRepository:
    """Data access layer for modernization documents."""

    def __init__(self, session: Session):
        self.session = session

    def create(
        self,
        name: str,
        modernization_goals: Optional[str],
        description: Optional[str] = None,
        linked_prds: Optional[list[str]] = None,
    ) -> ModernizationDocRecord:
        """Create a new modernization document."""
        doc = ModernizationDocRecord(
            name=name,
            description=description,
            modernization_goals=modernization_goals,
            linked_prds=linked_prds or [],
            status="draft",
        )
        self.session.add(doc)
        self.session.flush()
        return doc

    def get_by_id(self, doc_id: str) -> Optional[ModernizationDocRecord]:
        """Get a modernization document by ID."""
        return self.session.query(ModernizationDocRecord).filter(
            ModernizationDocRecord.id == doc_id
        ).first()

    def list_all(self, status: Optional[str] = None) -> list[ModernizationDocRecord]:
        """List all modernization documents, optionally filtered by status."""
        query = self.session.query(ModernizationDocRecord).order_by(
            ModernizationDocRecord.created_at.desc()
        )
        if status:
            query = query.filter(ModernizationDocRecord.status == status)
        return query.all()

    def update_status(
        self,
        doc_id: str,
        new_status: str,
        reviewed_by: Optional[str] = None,
        review_comment: Optional[str] = None,
    ) -> Optional[ModernizationDocRecord]:
        """Update document status and approval information."""
        doc = self.get_by_id(doc_id)
        if not doc:
            return None

        doc.status = new_status
        if reviewed_by:
            doc.reviewed_by = reviewed_by
        if review_comment:
            doc.review_comment = review_comment

        self.session.add(doc)
        self.session.flush()
        return doc

    def delete(self, doc_id: str) -> bool:
        """Delete a modernization document."""
        doc = self.get_by_id(doc_id)
        if not doc:
            return False

        self.session.delete(doc)
        self.session.flush()
        return True

    def get_draft_count(self) -> int:
        """Get count of draft documents."""
        return self.session.query(ModernizationDocRecord).filter(
            ModernizationDocRecord.status == "draft"
        ).count()

    def get_pending_approval_count(self) -> int:
        """Get count of documents pending approval."""
        return self.session.query(ModernizationDocRecord).filter(
            ModernizationDocRecord.status == "pending_approval"
        ).count()

    def get_approved_count(self) -> int:
        """Get count of approved documents."""
        return self.session.query(ModernizationDocRecord).filter(
            ModernizationDocRecord.status == "approved"
        ).count()

    def get_rejected_count(self) -> int:
        """Get count of rejected documents."""
        return self.session.query(ModernizationDocRecord).filter(
            ModernizationDocRecord.status == "rejected"
        ).count()
