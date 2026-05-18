"""Service layer for modernization document operations."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from backlog_generation.db import get_session
from modernization.models import ModernizationDocRecord
from approval.models import ApprovalEvent
from api.schemas.modernization_schemas import (
    ModernizationDocResponse,
    ModernizationDocListItem,
    FileUploadResponse,
    SourceAsset,
    LinkedPrd,
)
from api.services.prd_service import get_prd


def _resolve_prd_names(prd_ids: list[str]) -> list[LinkedPrd]:
    """Resolve PRD IDs to LinkedPrd objects with names.
    
    Falls back to ID if PRD not found.
    """
    linked_prds = []
    for prd_id in prd_ids:
        try:
            prd = get_prd(prd_id)
            linked_prds.append(LinkedPrd(id=prd_id, prd_name=prd.prd_name))
        except (FileNotFoundError, Exception):
            # Fallback if PRD not found
            linked_prds.append(LinkedPrd(id=prd_id, prd_name=f"PRD ({prd_id[:8]}...)"))
    return linked_prds


def create_modernization_doc(name: str, modernization_goals: Optional[str] = None, description: Optional[str] = None, linked_prds: Optional[list] = None) -> ModernizationDocResponse:
    """Create a new modernization document."""
    with get_session() as session:
        now = datetime.now(timezone.utc)
        doc = ModernizationDocRecord(
            name=name,
            description=description,
            modernization_goals=modernization_goals,
            linked_prds=linked_prds or [],
            status="draft",
            created_at=now,
            updated_at=now,
        )
        session.add(doc)
        session.flush()
        
        return ModernizationDocResponse(
            id=doc.id,
            name=doc.name,
            description=doc.description,
            status=doc.status,
            modernization_goals=doc.modernization_goals,
            linked_prds=_resolve_prd_names(doc.linked_prds or []),
            source_assets=[],
            generated_sections={},
            created_at=doc.created_at,
            updated_at=doc.updated_at,
            submitted_by=doc.submitted_by,
            reviewed_by=doc.reviewed_by,
            review_comment=doc.review_comment,
        )


def list_modernization_docs(status_filter: Optional[str] = None, skip: int = 0, limit: int = 20) -> list[ModernizationDocListItem]:
    """List modernization documents with optional filtering and pagination."""
    with get_session() as session:
        query = session.query(ModernizationDocRecord).order_by(ModernizationDocRecord.created_at.desc())
        
        if status_filter:
            query = query.filter(ModernizationDocRecord.status == status_filter)
        
        docs = query.offset(skip).limit(limit).all()
        
        return [
            ModernizationDocListItem(
                id=doc.id,
                name=doc.name,
                description=doc.description,
                status=doc.status,
                created_at=doc.created_at,
                updated_at=doc.updated_at,
                submitted_by=doc.submitted_by,
                reviewed_by=doc.reviewed_by,
            )
            for doc in docs
        ]


def get_modernization_doc(doc_id: str) -> ModernizationDocResponse:
    """Get a specific modernization document."""
    with get_session() as session:
        doc = session.query(ModernizationDocRecord).filter(ModernizationDocRecord.id == doc_id).first()
        
        if not doc:
            return None
        
        return ModernizationDocResponse(
            id=doc.id,
            name=doc.name,
            description=doc.description,
            status=doc.status,
            modernization_goals=doc.modernization_goals,
            linked_prds=_resolve_prd_names(doc.linked_prds or []),
            source_assets=[SourceAsset(**asset) for asset in (doc.source_assets or [])],
            generated_sections=doc.generated_sections or {},
            created_at=doc.created_at,
            updated_at=doc.updated_at,
            submitted_at=doc.submitted_at,
            submitted_by=doc.submitted_by,
            reviewed_by=doc.reviewed_by,
            review_comment=doc.review_comment,
        )


def update_modernization_doc(doc_id: str, name: Optional[str] = None, description: Optional[str] = None, modernization_goals: Optional[str] = None, linked_prds: Optional[list] = None) -> ModernizationDocResponse:
    """Update a modernization document."""
    with get_session() as session:
        doc = session.query(ModernizationDocRecord).filter(ModernizationDocRecord.id == doc_id).first()
        
        if not doc:
            return None
        
        if doc.status != "draft":
            raise ValueError("Only draft documents can be edited")
        
        if name is not None:
            doc.name = name
        if description is not None:
            doc.description = description
        if modernization_goals is not None:
            doc.modernization_goals = modernization_goals
        if linked_prds is not None:
            doc.linked_prds = linked_prds
        
        doc.updated_at = datetime.now(timezone.utc)
        session.add(doc)
        session.flush()
        
        return ModernizationDocResponse(
            id=doc.id,
            name=doc.name,
            description=doc.description,
            status=doc.status,
            modernization_goals=doc.modernization_goals,
            linked_prds=_resolve_prd_names(doc.linked_prds or []),
            source_assets=[SourceAsset(**asset) for asset in (doc.source_assets or [])],
            generated_sections=doc.generated_sections or {},
            created_at=doc.created_at,
            updated_at=doc.updated_at,
            submitted_by=doc.submitted_by,
            reviewed_by=doc.reviewed_by,
            review_comment=doc.review_comment,
        )


def delete_modernization_doc(doc_id: str) -> bool:
    """Delete a modernization document."""
    with get_session() as session:
        doc = session.query(ModernizationDocRecord).filter(ModernizationDocRecord.id == doc_id).first()
        
        if not doc:
            return False
        
        if doc.status != "draft":
            raise ValueError("Only draft documents can be deleted")
        
        if doc.source_assets:
            for asset in doc.source_assets:
                try:
                    Path(asset.get("path", "")).unlink(missing_ok=True)
                except Exception:
                    pass
        
        session.delete(doc)
        session.flush()
        return True


def add_source_asset(doc_id: str, filename: str, file_path: str, size: int) -> FileUploadResponse:
    """Add a source asset to a modernization document."""
    with get_session() as session:
        doc = session.query(ModernizationDocRecord).filter(ModernizationDocRecord.id == doc_id).first()
        
        if not doc:
            return None
        
        if doc.status != "draft":
            raise ValueError("Can only upload files to draft documents")
        
        if not doc.source_assets:
            doc.source_assets = []
        
        now = datetime.now(timezone.utc)
        asset = {
            "filename": filename,
            "path": file_path,
            "uploaded_at": now.isoformat(),
            "size": size,
        }
        doc.source_assets.append(asset)
        doc.updated_at = now
        session.add(doc)
        session.flush()
        
        return FileUploadResponse(
            filename=filename,
            path=file_path,
            size=size,
            uploaded_at=now.isoformat(),
        )


def remove_source_asset(doc_id: str, filename: str) -> bool:
    """Remove a source asset from a modernization document."""
    with get_session() as session:
        doc = session.query(ModernizationDocRecord).filter(ModernizationDocRecord.id == doc_id).first()
        
        if not doc:
            return False
        
        if doc.status != "draft":
            raise ValueError("Can only delete files from draft documents")
        
        found = False
        if doc.source_assets:
            for i, asset in enumerate(doc.source_assets):
                if asset.get("filename") == filename:
                    file_path = asset.get("path")
                    if file_path:
                        try:
                            Path(file_path).unlink(missing_ok=True)
                        except Exception:
                            pass
                    doc.source_assets.pop(i)
                    found = True
                    break
        
        if not found:
            return False
        
        doc.updated_at = datetime.now(timezone.utc)
        session.add(doc)
        session.flush()
        return True


def submit_for_approval(doc_id: str, submitted_by: str, comment: Optional[str] = None) -> ModernizationDocResponse:
    """Submit a modernization document for approval."""
    with get_session() as session:
        doc = session.query(ModernizationDocRecord).filter(ModernizationDocRecord.id == doc_id).first()
        
        if not doc:
            return None
        
        if doc.status not in ["draft", "rejected"]:
            raise ValueError("Only draft or rejected documents can be submitted")
        
        previous_status = doc.status
        now = datetime.now(timezone.utc)
        doc.status = "pending_approval"
        doc.submitted_by = submitted_by
        doc.submitted_at = now
        doc.updated_at = now
        
        session.add(doc)
        session.flush()
        
        # Create approval event
        approval_event = ApprovalEvent(
            artifact_type="modernization",
            artifact_id=doc.id,
            artifact_name=doc.name,
            from_status=previous_status,
            to_status="pending_approval",
            submitted_by=submitted_by,
            comment=comment or "Submitted for approval",
        )
        session.add(approval_event)
        session.flush()
        
        return ModernizationDocResponse(
            id=doc.id,
            name=doc.name,
            description=doc.description,
            status=doc.status,
            modernization_goals=doc.modernization_goals,
            linked_prds=_resolve_prd_names(doc.linked_prds or []),
            source_assets=[SourceAsset(**asset) for asset in (doc.source_assets or [])],
            generated_sections=doc.generated_sections or {},
            created_at=doc.created_at,
            updated_at=doc.updated_at,
            submitted_at=doc.submitted_at,
            submitted_by=doc.submitted_by,
            reviewed_by=doc.reviewed_by,
            review_comment=doc.review_comment,
        )


def review_modernization_doc(doc_id: str, action: str, reviewed_by: str, comment: str) -> ModernizationDocResponse:
    """Review a modernization document."""
    with get_session() as session:
        doc = session.query(ModernizationDocRecord).filter(ModernizationDocRecord.id == doc_id).first()
        
        if not doc:
            return None
        
        if doc.status != "pending_approval":
            raise ValueError("Only pending documents can be reviewed")
        
        new_status = "approved" if action == "approve" else "rejected"
        doc.status = new_status
        doc.reviewed_by = reviewed_by
        doc.review_comment = comment
        doc.updated_at = datetime.now(timezone.utc)
        
        session.add(doc)
        session.flush()
        
        # Create approval event

        approval_event = ApprovalEvent(
            artifact_type="modernization",
            artifact_id=doc.id,
            artifact_name=doc.name,
            from_status="pending_approval",
            to_status=new_status,
            reviewed_by=reviewed_by,
            comment=comment,
        )
        session.add(approval_event)
        session.flush()
        
        return ModernizationDocResponse(
            id=doc.id,
            name=doc.name,
            description=doc.description,
            status=doc.status,
            modernization_goals=doc.modernization_goals,
            linked_prds=_resolve_prd_names(doc.linked_prds or []),
            source_assets=[SourceAsset(**asset) for asset in (doc.source_assets or [])],
            generated_sections=doc.generated_sections or {},
            created_at=doc.created_at,
            updated_at=doc.updated_at,
            submitted_at=doc.submitted_at,
            submitted_by=doc.submitted_by,
            reviewed_by=doc.reviewed_by,
            review_comment=doc.review_comment,
        )
