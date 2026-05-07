import git
import shutil
import uuid
from datetime import datetime
import json
from pathlib import Path
from uuid import UUID

from api.models import PrdItem, PrdListItem
from config import get_settings
from utils.document_utils import extract_documents_from_uploads
from backlog_generation.db import get_session
from prd_generation.prd_repository import (
    create_prd,
    get_prd as db_get_prd,
    list_prds as db_list_prds,
    update_prd_status,
    get_prd_approval_history,
)

# Expected section order for PRD content
EXPECTED_SECTION_ORDER = [
    "Executive Summary",
    "System Overview",
    "Functional Requirements",
    "Data Model",
    "Process Flows",
    "Business Rules",
    "External Interfaces",
    "Non Functional Requirements",
    "Risks",
]


def order_prd_sections(prd_dict: dict) -> dict:
    """Reorder and format PRD dict keys to match expected section order.
    
    Args:
        prd_dict: PRD content dict with potentially unordered keys (snake_case or Title Case)
        
    Returns:
        Dict with keys in expected section order and formatted as Title Case
    """
    # Normalize all keys: convert snake_case to Title Case for comparison
    normalized = {}
    for key, value in prd_dict.items():
        normalized_key = key.replace('_', ' ').title()
        normalized[normalized_key] = value
    
    ordered = {}
    
    # Add sections in expected order
    for section in EXPECTED_SECTION_ORDER:
        if section in normalized:
            ordered[section] = normalized[section]
    
    for key, value in normalized.items():
        if key not in ordered:
            ordered[key] = value
    
    return ordered


def clone_repository(url: str) -> str:
    """Clone a GitHub repository into the workspace directory.

    Args:
        url: A validated GitHub URL.

    Returns:
        Absolute path string of the cloned directory.

    Raises:
        ValueError: If the git clone fails.
    """
    s = get_settings()
    workspace_dir = s.WORKSPACE_DIR
    workspace_dir.mkdir(parents=True, exist_ok=True)

    repo_name = url.rstrip("/").split("/")[-1].replace(".git", "")
    clone_dir = workspace_dir / repo_name

    if clone_dir.exists():
        shutil.rmtree(clone_dir)

    try:
        git.Repo.clone_from(url, str(clone_dir))
    except git.GitCommandError as e:
        raise ValueError(f"Failed to clone repository: {e.stderr}") from e

    return str(clone_dir)


def extract_and_validate_documents(doc_refs: list[dict]) -> list[dict[str, str]]:
    """Extract documents from the uploads directory and validate they have sufficient content.

    Args:
        doc_refs: List of document reference dicts (id, name, etc.) from the request.

    Returns:
        List of {filename, content} dicts.

    Raises:
        ValueError: If extraction fails or content is insufficient.
    """
    uploads_dir = get_settings().UPLOADS_DIR
    documents = extract_documents_from_uploads(uploads_dir, doc_refs)
    total_length = sum(len(doc.get("content", "")) for doc in documents)
    if not documents or total_length < 100:
        raise ValueError(
            f"Document extraction failed or insufficient content. "
            f"Extracted: {total_length} chars from {len(documents)} documents."
        )
    return documents


def save_prd(
    prd_data: dict,
    source_files: list[str] | None = None,
    prd_name: str | None = None,
) -> tuple[str, dict, str, str]:
    """Persist a PRD to database and disk as JSON, returning parsed structure.

    Args:
        prd_data: A dict of the PRD content (JSON object).
        source_files: Optional list of source file names.

    Returns:
        Tuple of (prd_id, prd_json, filename, prd_name) where prd_id is the database
        record ID, prd_json is the parsed content, filename is the disk filename,
        and prd_name is the stored display name.
    """
    # Use dict directly as JSON
    prd_json = prd_data if isinstance(prd_data, dict) else {"content": str(prd_data)}
    normalized_prd_name = (prd_name or "").strip() or "Untitled PRD"
    
    # Store in database
    with get_session() as session:
        prd_record = create_prd(
            session,
            prd_name=normalized_prd_name,
            source_files=source_files or [],
            prd_content=prd_json
        )
        prd_id = str(prd_record.id)
    
    # Also save to disk for backward compatibility
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    unique_id = uuid.uuid4().hex[:8]
    filename = f"prd_{timestamp}_{unique_id}.json"
    filepath = get_settings().GENERATED_PRDS_DIR / filename
    filepath.write_text(json.dumps(prd_json, indent=2))    
    return prd_id, prd_json, filename, normalized_prd_name


def list_prds() -> list[PrdListItem]:
    """Return all saved PRDs from database sorted by creation time descending."""
    with get_session() as session:
        prd_records = db_list_prds(session)
        return [
            PrdListItem(
                id=str(prd['id']),
                prd_name=prd.get('prd_name') or "Untitled PRD",
                filename=f"prd_{datetime.fromisoformat(prd['created_at']).strftime('%Y%m%d_%H%M%S')}.json",
                status=prd['status']
            )
            for prd in prd_records
        ]


def get_prd(prd_id: str) -> PrdItem:
    """Load a PRD by ID from database.

    Args:
        prd_id: UUID of the PRD record.

    Raises:
        FileNotFoundError: If the PRD does not exist.
    """
    with get_session() as session:
        prd_record = db_get_prd(session, UUID(prd_id))
        if not prd_record:
            raise FileNotFoundError(prd_id)
        
        filename = f"prd_{prd_record.created_at.strftime('%Y%m%d_%H%M%S')}.json" if prd_record.created_at else f"prd_{prd_id}.json"
        ordered_content = order_prd_sections(prd_record.prd_content or {})
        
        return PrdItem(
            id=str(prd_record.id),
            prd_name=prd_record.prd_name or "Untitled PRD",
            filename=filename,
            content=ordered_content,
            generated_time=prd_record.created_at.timestamp() if prd_record.created_at else datetime.now().timestamp(),
            status=prd_record.status,
            reviewed_by=prd_record.reviewed_by,
            review_comment=prd_record.review_comment,
            reviewed_at=prd_record.reviewed_at.isoformat() if prd_record.reviewed_at else None,
        )


def set_prd_status(
    prd_id: str,
    new_status: str,
    reviewed_by: str | None = None,
    review_comment: str | None = None,
) -> dict:
    """Transition a PRD to a new status (approve/reject).
    
    Args:
        prd_id: UUID of the PRD record.
        new_status: Target status (approved, rejected, etc.).
        reviewed_by: Name of the reviewer.
        review_comment: Reviewer's comment.
        
    Returns:
        Dict with updated PRD details including new status and reviewer info.
        
    Raises:
        FileNotFoundError: If PRD not found.
        ValueError: If transition not allowed.
    """
    with get_session() as session:
        updated_record = update_prd_status(
            session,
            prd_id,
            new_status,
            reviewed_by=reviewed_by,
            review_comment=review_comment,
        )
        session.commit()
        
        filename = f"prd_{updated_record.created_at.strftime('%Y%m%d_%H%M%S')}.json" if updated_record.created_at else f"prd_{prd_id}.json"
        
        return {
            "id": str(updated_record.id),
            "filename": filename,
            "status": updated_record.status,
            "reviewed_by": updated_record.reviewed_by,
            "review_comment": updated_record.review_comment,
            "reviewed_at": updated_record.reviewed_at.isoformat() if updated_record.reviewed_at else None,
            "created_at": updated_record.created_at.isoformat(),
        }


def get_prd_approvals(prd_id: str) -> list[dict]:
    """Get approval history for a PRD.
    
    Args:
        prd_id: UUID of the PRD record.
        
    Returns:
        List of approval event dicts ordered chronologically.
    """
    with get_session() as session:
        events = get_prd_approval_history(session, prd_id)
        return [
            {
                "id": str(e.id),
                "prd_id": str(e.prd_id),
                "from_status": e.from_status,
                "to_status": e.to_status,
                "submitted_by": e.submitted_by,
                "reviewed_by": e.reviewed_by,
                "comment": e.comment,
                "created_at": e.created_at.isoformat(),
            }
            for e in events
        ]
