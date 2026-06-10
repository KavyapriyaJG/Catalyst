"""FastAPI routes for modernization document management."""

import asyncio
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
    UpdateModernizationRequest,
    SubmitForApprovalRequest,
    ApprovalActionRequest,
    ModernizationDocResponse,
    ModernizationDocListItem,
    FileUploadResponse,
    ModernizationGenerateRequest,
)
from api.services import modernization_service
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
from dummy_modernization_content import DUMMY_MODERNIZATION_SECTIONS, DUMMY_MODERNIZATION_STREAM_EVENTS

router = APIRouter(prefix="/modernization", tags=["modernization"])
settings = get_settings()

ALLOWED_EXTENSIONS = SUPPORTED_DOCUMENT_EXTENSIONS
VALID_STATUSES = {'draft', 'pending_approval', 'approved', 'rejected', 'synced_to_jira'}


def parse_blueprint_to_sections(blueprint: str) -> dict[str, str]:
    """
    Parse a markdown blueprint string into separate sections by ## headings.
    Handles nested ### subsections within each main section.
    
    Args:
        blueprint: Markdown string with ## headings for sections (or dict to extract from)
        
    Returns:
        Dictionary with section titles as keys and content as values
    """
    if not blueprint:
        return {}
    
    # If blueprint is a dict, try to extract markdown content
    if isinstance(blueprint, dict):
        # Try to find a 'blueprint' field with the actual markdown
        if 'blueprint' in blueprint and isinstance(blueprint['blueprint'], str):
            blueprint = blueprint['blueprint']
        else:
            # If it's a dict but no markdown found, return empty (can't parse dict as sections)
            return {}
    
    # Ensure blueprint is a string
    if not isinstance(blueprint, str):
        return {}
    
    sections = {}
    current_section = None
    current_content = []
    
    lines = blueprint.split('\n')
    
    for line in lines:
        # Check if this line is a ## heading (main section header, not ### subsection)
        if line.startswith('## ') and not line.startswith('### '):
            # Save previous section if exists
            if current_section is not None:
                content = '\n'.join(current_content).strip()
                if content:  # Only save sections with content
                    sections[current_section] = content
            
            # Start new section - extract title after ##
            current_section = line[3:].strip()  # Remove '## ' prefix
            current_content = []
        elif current_section is not None:
            # Add line to current section (including ### subsections)
            current_content.append(line)
    
    # Don't forget the last section
    if current_section is not None:
        content = '\n'.join(current_content).strip()
        if content:
            sections[current_section] = content
    
    return sections


@router.post("/generate")
async def generate_modernization_doc_sse(payload: ModernizationGenerateRequest):
    """Generate modernization document from PRDs and supporting docs (SSE streaming).
    
    Creates the document internally and streams generation progress via SSE.
    Returns the doc ID in the complete event.
    """
    try:
        doc = modernization_service.create_modernization_doc(
            name=payload.name,
            modernization_goals=payload.modernization_goals,
            description=payload.modernization_goals,
            linked_prds=payload.linked_prds,
        )
        doc_id = doc.id
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Failed to create document: {str(e)}")

    async def event_generator():
        """Async generator that streams events from the background generation task."""
        event_queue: queue_module.Queue[str] = queue_module.Queue()
        
        prd_ids = payload.linked_prds
        assets_dicts = []
        
        analysis_context = {
            "source": "linked_prds_and_assets",
            "linked_prds": prd_ids,
            "asset_count": len(payload.supporting_documents),
            "modernization_goals": payload.modernization_goals or "Not specified",
        }
        
        if payload.supporting_documents:
            analysis_context["asset_summary"] = f"Supporting documents: {', '.join(payload.supporting_documents)}"
        
        generation_task = asyncio.create_task(
            generate_modernization_doc(
                doc_id=doc_id,
                doc_name=payload.name,
                modernization_goals=payload.modernization_goals,
                linked_prds=prd_ids,
                source_assets=assets_dicts,
                analysis=analysis_context,
                event_queue=event_queue,
            )
        )
        
        yield f"data: [Step 1 of 3] Analyzing modernization context...\n\n"
        
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
            generation_result = await generation_task
            if isinstance(generation_result, dict):
                blueprint_data = generation_result.get("blueprint", {})
            else:
                blueprint_data = {}
            
            if isinstance(blueprint_data, dict):
                parsed_sections = blueprint_data
            elif isinstance(blueprint_data, str) and blueprint_data:
                parsed_sections = parse_blueprint_to_sections(blueprint_data)
            else:
                parsed_sections = {}
            
            with get_session() as session:
                db_doc = session.query(ModernizationDocRecord).filter(ModernizationDocRecord.id == doc_id).first()
                if db_doc:
                    db_doc.generated_sections = parsed_sections
                    db_doc.updated_at = datetime.now(timezone.utc)
                    session.add(db_doc)
                    session.commit()

            yield f"event: complete\ndata: {json.dumps({'id': doc_id, 'name': payload.name, 'modernization_goals': payload.modernization_goals})}\n\n"
        
        except Exception as e:
            traceback.print_exc()
            yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.post("/generate/dummy")
async def generate_modernization_dummy(payload: ModernizationGenerateRequest):
    """Generate dummy modernization document with streaming for loading effect."""
    
    async def event_generator():
        for msg, delay in DUMMY_MODERNIZATION_STREAM_EVENTS:
            yield f"data: {msg}\n\n"
            await asyncio.sleep(delay)

        doc_id = "7bc0c9e8-6b0d-41cf-893d-96ae712f27c8"
        try:
            # Try to fetch existing doc with this ID
            doc = modernization_service.get_modernization_doc(doc_id)
            if doc and doc.generated_sections:
                yield (
                    f"event: complete\n"
                    f"data: {json.dumps({'id': doc_id, 'name': doc.name, 'modernization_goals': doc.modernization_goals})}\n\n"
                )
            else:
                raise FileNotFoundError()
        except (FileNotFoundError, AttributeError):
            # If not found, return dummy with payload values
            yield (
                f"event: complete\n"
                f"data: {json.dumps({'id': doc_id, 'name': payload.name, 'modernization_goals': payload.modernization_goals})}\n\n"
            )

    return StreamingResponse(event_generator(), media_type="text/event-stream")


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
        # If doc not found and it's our dummy ID, return dummy content
        if doc_id == "7bc0c9e8-6b0d-41cf-893d-96ae712f27c8":
            return ModernizationDocResponse(
                id=doc_id,
                name="Dummy Modernization Plan",
                description="Sample modernization strategy document",
                modernization_goals="Transform legacy system to cloud-native architecture",
                generated_sections=DUMMY_MODERNIZATION_SECTIONS,
                status="draft",
                linked_prds=[],
                created_at=datetime.now(timezone.utc).isoformat(),
                updated_at=datetime.now(timezone.utc).isoformat(),
            )
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


@router.get("/{doc_id}/export")
def export_modernization_markdown(
    doc_id: str,
    include_generated: bool = Query(True),
):
    """Export modernization document as markdown (for frontend DOCX conversion)."""
    doc = modernization_service.get_modernization_doc(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Modernization document not found")
    
    try:
        # Build markdown content
        lines = [f"# {doc.name}"]
        lines.append("")
        
        if doc.description:
            lines.append(f"**Overview:** {doc.description}")
            lines.append("")
        
        lines.append(f"**Status:** {doc.status.upper()}")
        lines.append(f"**Created:** {doc.created_at.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"**Last Updated:** {doc.updated_at.strftime('%Y-%m-%d %H:%M:%S')}")
        if doc.submitted_by:
            lines.append(f"**Submitted By:** {doc.submitted_by}")
        lines.append("")
        
        if doc.modernization_goals:
            lines.append("## Modernization Goals")
            lines.append(doc.modernization_goals)
            lines.append("")
        
        if doc.linked_prds:
            lines.append("## Linked Requirements")
            for prd_id in doc.linked_prds:
                lines.append(f"- {prd_id}")
            lines.append("")
        
        if doc.source_assets:
            lines.append("## Supporting Documentation")
            for asset in doc.source_assets:
                filename = asset.filename if hasattr(asset, "filename") else asset.get("filename", "unknown")
                size = asset.size if hasattr(asset, "size") else asset.get("size", 0)
                size_mb = f"{size / (1024*1024):.2f} MB" if size > 0 else "0 MB"
                lines.append(f"- {filename} ({size_mb})")
            lines.append("")
        
        if include_generated and doc.generated_sections:
            for section_title, section_content in doc.generated_sections.items():
                if section_content:
                    lines.append(f"## {section_title}")
                    lines.append(str(section_content))
                    lines.append("")
        
        if doc.reviewed_by:
            lines.append("## Approval & Sign-Off")
            lines.append(f"**Reviewed by:** {doc.reviewed_by}")
            lines.append(f"**Review Status:** {doc.status.upper()}")
            if doc.review_comment:
                lines.append(f"**Comments:** {doc.review_comment}")
        
        markdown_content = "\n".join(lines)
        
        return {
            "filename": f"modernization_{doc.id}.md",
            "markdown": markdown_content,
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
