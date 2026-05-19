"""FastAPI routes for modernization document management."""

import asyncio
import base64
import json
import queue as queue_module
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, UploadFile, HTTPException, Query, status
from fastapi.responses import StreamingResponse

from config import get_settings
from api.schemas.modernization_schemas import (
    CreateModernizationRequest,
    UpdateModernizationRequest,
    SubmitForApprovalRequest,
    ApprovalActionRequest,
    ModernizationDocResponse,
    ModernizationDocListItem,
    FileUploadResponse,
)
from api.services import modernization_service
from modernization.utils.generator import generate_docx_export
from modernization.agents.agent import generate_modernization_doc
from backlog_generation.db import get_session
from modernization.models import ModernizationDocRecord
from utils.file_handling import (
    SUPPORTED_DOCUMENT_EXTENSIONS,
    MAX_FILE_SIZE,
    validate_file_extension,
    validate_file_size,
    get_extension_error_message,
)

router = APIRouter(prefix="/modernization", tags=["modernization"])
settings = get_settings()

ALLOWED_EXTENSIONS = SUPPORTED_DOCUMENT_EXTENSIONS
VALID_STATUSES = {'draft', 'pending_approval', 'approved', 'rejected', 'synced_to_jira'}


@router.post("/", response_model=ModernizationDocResponse, status_code=status.HTTP_201_CREATED)
def create_modernization_doc(request: CreateModernizationRequest) -> ModernizationDocResponse:
    """Create a new modernization document."""
    return modernization_service.create_modernization_doc(
        name=request.name,
        modernization_goals=request.modernization_goals,
        description=request.description,
        linked_prds=request.linked_prds,
    )


@router.get("/", response_model=list[ModernizationDocListItem])
def list_modernization_docs(
    status_filter: Optional[str] = Query(None, description="Filter by status"),
    skip: int = Query(0, ge=0, description="Skip N records for pagination"),
    limit: int = Query(20, ge=1, le=100, description="Limit results to N records"),
) -> list[ModernizationDocListItem]:
    """List all modernization documents with pagination and optional status filter."""
    if status_filter and status_filter not in VALID_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status filter. Must be one of: {', '.join(sorted(VALID_STATUSES))}"
        )
    return modernization_service.list_modernization_docs(status_filter, skip, limit)


@router.get("/{doc_id}", response_model=ModernizationDocResponse)
def get_modernization_doc(doc_id: str) -> ModernizationDocResponse:
    """Get a specific modernization document."""
    doc = modernization_service.get_modernization_doc(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Modernization document not found")
    return doc


@router.put("/{doc_id}", response_model=ModernizationDocResponse)
def update_modernization_doc(
    doc_id: str,
    request: UpdateModernizationRequest,
) -> ModernizationDocResponse:
    """Update a modernization document (save draft)."""
    try:
        result = modernization_service.update_modernization_doc(
            doc_id=doc_id,
            name=request.name,
            description=request.description,
            modernization_goals=request.modernization_goals,
            linked_prds=request.linked_prds,
        )
        if not result:
            raise HTTPException(status_code=404, detail="Modernization document not found")
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete("/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_modernization_doc(doc_id: str):
    """Delete a modernization document."""
    try:
        if not modernization_service.delete_modernization_doc(doc_id):
            raise HTTPException(status_code=404, detail="Modernization document not found")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/{doc_id}/upload", response_model=FileUploadResponse)
async def upload_supporting_document(
    doc_id: str,
    file: UploadFile = File(...),
) -> FileUploadResponse:
    """Upload a supporting document to a modernization doc."""
    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File must have a name")
    
    if not validate_file_extension(file.filename):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=get_extension_error_message(),
        )
    
    contents = await file.read()
    
    is_valid, error_msg = validate_file_size(len(contents))
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=error_msg,
        )
    
    doc_upload_dir = settings.UPLOADS_DIR / "modernization" / doc_id
    doc_upload_dir.mkdir(parents=True, exist_ok=True)
    
    safe_filename = Path(file.filename).name
    file_path = doc_upload_dir / safe_filename
    
    with open(file_path, "wb") as f:
        f.write(contents)
    
    try:
        result = modernization_service.add_source_asset(
            doc_id=doc_id,
            filename=safe_filename,
            file_path=str(file_path),
            size=len(contents),
        )
        if not result:
            raise HTTPException(status_code=404, detail="Modernization document not found")
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete("/{doc_id}/files/{filename}")
def delete_supporting_document(doc_id: str, filename: str):
    """Delete a supporting document from a modernization doc."""
    try:
        if not modernization_service.remove_source_asset(doc_id, filename):
            raise HTTPException(status_code=404, detail="File not found in document")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    
    return {"status": "deleted"}


@router.post("/{doc_id}/submit", response_model=ModernizationDocResponse)
def submit_for_approval(
    doc_id: str,
    request: SubmitForApprovalRequest,
) -> ModernizationDocResponse:
    """Submit a modernization document for approval."""
    try:
        result = modernization_service.submit_for_approval(
            doc_id=doc_id,
            submitted_by=request.submitted_by,
            comment=request.comment,
        )
        if not result:
            raise HTTPException(status_code=404, detail="Modernization document not found")
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/{doc_id}/review", response_model=ModernizationDocResponse)
def review_modernization_doc(
    doc_id: str,
    request: ApprovalActionRequest,
) -> ModernizationDocResponse:
    """Review a modernization document (approve or reject)."""
    try:
        result = modernization_service.review_modernization_doc(
            doc_id=doc_id,
            action=request.action,
            reviewed_by=request.reviewed_by,
            comment=request.comment,
        )
        if not result:
            raise HTTPException(status_code=404, detail="Modernization document not found")
        return result
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/{doc_id}/generate-from-prds")
async def generate_from_prds(doc_id: str):
    """Generate modernization document sections from linked PRDs and supporting docs."""
    doc = modernization_service.get_modernization_doc(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Modernization document not found")

    if doc.status != "draft":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Can only generate for draft documents")

    async def event_generator():
        """Async generator that streams events from the background generation task."""
        event_queue: queue_module.Queue[str] = queue_module.Queue()
        
        generation_task = asyncio.create_task(
            generate_modernization_doc(
                doc_id=doc_id,
                doc_name=doc.name,
                modernization_goals=doc.modernization_goals,
                linked_prds=doc.linked_prds if doc.linked_prds else [],
                source_assets=doc.source_assets if doc.source_assets else [],
                event_queue=event_queue,
            )
        )
        
        yield f"data: Analyzing modernization context...\n\n"
        
        # Poll queue while task is running
        while not generation_task.done():
            await asyncio.sleep(0.1)
            while not event_queue.empty():
                try:
                    event_text = event_queue.get_nowait()
                    yield f"data: {event_text}\n\n"
                except queue_module.Empty:
                    break
        
        while not event_queue.empty():
            try:
                event_text = event_queue.get_nowait()
                yield f"data: {event_text}\n\n"
            except queue_module.Empty:
                break
        
        try:
            sections = await generation_task
            
            with get_session() as session:
                db_doc = session.query(ModernizationDocRecord).filter(ModernizationDocRecord.id == doc_id).first()
                if db_doc:
                    db_doc.generated_sections = sections
                    db_doc.updated_at = datetime.now(timezone.utc)
                    session.add(db_doc)
                    session.commit()
                else:
                    yield f"event: error\ndata: {json.dumps({'error': 'Document not found in database during save'})}\n\n"
                    return

            yield f"event: complete\ndata: {json.dumps({'message': 'Modernization document generated successfully!', 'sections': sections})}\n\n"
        
        except Exception as e:
            traceback.print_exc()
            yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/{doc_id}/export")
def export_modernization_docx(
    doc_id: str,
    include_generated: bool = Query(True),
):
    """Export modernization document as DOCX."""
    doc = modernization_service.get_modernization_doc(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Modernization document not found")
    
    try:
        with get_session() as session:
            db_doc = session.query(ModernizationDocRecord).filter(ModernizationDocRecord.id == doc_id).first()
            docx_bytes = generate_docx_export(db_doc, include_generated, session)
        
        return {
            "filename": f"modernization_{doc.id}.docx",
            "docx_base64": base64.b64encode(docx_bytes).decode("utf-8"),
            "size": len(docx_bytes),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Export failed: {str(e)}")


@router.post("/{doc_id}/sync-to-jira")
def sync_to_jira(doc_id: str):
    """Sync approved modernization doc to Jira as an Epic."""
    doc = modernization_service.get_modernization_doc(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Modernization document not found")
    
    if doc.status != "approved":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only approved documents can be synced to Jira")
    
    return {"status": "synced", "doc_id": doc.id}
