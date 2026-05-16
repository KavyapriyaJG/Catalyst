import asyncio
import json
import logging
import os
import queue as queue_module
import re
import traceback
import uuid

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from pydantic import BaseModel

from api.models import PrdGenerateRequest, PrdItem, PrdListItem, PrdStatusUpdate
from dummy_prd_content import DUMMY_PRD_STREAM_EVENTS, DUMMY_PRD_TEXT
from prd_generation.prd_generation_graph import run_prd_pipeline
from api.services.prd_service import clone_repository, extract_and_validate_documents, get_prd, list_prds, save_prd, set_prd_status, get_prd_approvals, list_comments, add_comment, remove_comment


class CreateCommentRequest(BaseModel):
    section_id: str
    section_title: str
    author: str
    text: str
    parent_id: str | None = None

router = APIRouter(prefix="/prd", tags=["prd"])
logger = logging.getLogger(__name__)


def _resolve_priority_mode(payload: PrdGenerateRequest) -> str:
    """Resolve mutually-exclusive source priority mode from request flags."""
    if payload.prioritize_code and payload.prioritize_documents:
        raise HTTPException(
            status_code=400,
            detail="Select only one priority toggle: prioritize_code or prioritize_documents",
        )
    if payload.prioritize_code:
        return "code_high"
    if payload.prioritize_documents:
        return "docs_high"
    return "auto_bias"

def _resolve_prd_inputs(payload: PrdGenerateRequest) -> tuple[str | None, list[dict]]:
    """Validate and resolve the PRD request into an input_path and parsed documents.

    Raises HTTPException for any invalid input.
    """
    if not payload.input_path and not payload.github_urls and not payload.documents:
        raise HTTPException(
            status_code=400, detail="Provide either input_path, github_urls, or documents"
        )

    input_path = payload.input_path

    if payload.github_urls:
        url = payload.github_urls[0].strip()
        if not re.match(r"^https://[a-zA-Z0-9._-]+(/[a-zA-Z0-9._-]+)+(?:\.git)?$", url):
            raise HTTPException(status_code=400, detail=f"Invalid GitHub URL format: {url}")
        try:
            input_path = clone_repository(url)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    if input_path and not os.path.isdir(input_path):
        raise HTTPException(status_code=400, detail=f"Path does not exist: {input_path}")

    parsed_documents: list[dict] = []
    if payload.documents:
        try:
            parsed_documents = extract_and_validate_documents(payload.documents)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    return input_path, parsed_documents


async def _stream_prd_pipeline(
    input_path: str | None,
    prd_name: str | None,
    github_urls: list[str] | None,
    documents: list[dict],
    priority_mode: str,
):
    """Async generator that runs the PRD pipeline and yields SSE-formatted messages."""
    event_queue: queue_module.Queue[str] = queue_module.Queue()
    pipeline_task = asyncio.create_task(
        run_prd_pipeline(
            input_path=input_path,
            github_urls=github_urls,
            documents=documents,
            priority_mode=priority_mode,
            event_queue=event_queue,
        )
    )

    while not pipeline_task.done():
        await asyncio.sleep(0.1)
        while not event_queue.empty():
            try:
                yield f"data: {event_queue.get_nowait()}\n\n"
            except queue_module.Empty:
                break

    while not event_queue.empty():
        try:
            yield f"data: {event_queue.get_nowait()}\n\n"
        except queue_module.Empty:
            break

    try:
        prd_json = pipeline_task.result()
        prd_id, prd_json, filename, stored_prd_name = save_prd(prd_json, prd_name=prd_name)
        yield f"event: complete\ndata: {json.dumps({'prd': prd_json, 'id': prd_id, 'filename': filename, 'prd_name': stored_prd_name})}\n\n"
    except Exception as error:
        trace_id = str(uuid.uuid4())
        tb = traceback.format_exc()
        logger.error("PRD generation failed [trace_id=%s]: %s", trace_id, str(error))
        logger.error("PRD generation traceback [trace_id=%s]\n%s", trace_id, tb)
        error_payload = {
            "error": str(error),
            "error_type": type(error).__name__,
            "trace_id": trace_id,
        }
        yield f"event: error\ndata: {json.dumps(error_payload)}\n\n"


@router.post("/generate")
async def generate_prd_sse(payload: PrdGenerateRequest):
    priority_mode = _resolve_priority_mode(payload)
    input_path, parsed_documents = _resolve_prd_inputs(payload)
    return StreamingResponse(
        _stream_prd_pipeline(
            input_path,
            payload.prd_name,
            payload.github_urls,
            parsed_documents,
            priority_mode,
        ),
        media_type="text/event-stream",
    )


@router.post("/generate/dummy")
async def generate_prd_sse_dummy(_payload: PrdGenerateRequest):
    """Dummy endpoint that replays the real /prd/generate SSE stream with artificial delays."""
    _ = _resolve_priority_mode(_payload)

    async def event_generator():
        for msg, delay in DUMMY_PRD_STREAM_EVENTS:
            yield f"data: {msg}\n\n"
            await asyncio.sleep(delay)

        prd_dict = DUMMY_PRD_TEXT
        prd_id, prd_json, filename, stored_prd_name = save_prd(prd_dict, prd_name=_payload.prd_name)
        
        yield (
            f"event: complete\n"
            f"data: {json.dumps({'prd': prd_json, 'id': prd_id, 'filename': filename, 'prd_name': stored_prd_name})}\n\n"
        )

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/list", response_model=list[PrdListItem])
def get_prds_list():
    return list_prds()


@router.get("/{prd_id}", response_model=PrdItem)
def get_prd_by_id(prd_id: str):
    try:
        return get_prd(prd_id)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=f"PRD not found: {error}") from error


@router.patch(
    "/{prd_id}/status",
    response_model=dict,
    summary="Transition PRD status (draft→pending_review→approved|rejected→published)",
)
def update_prd_status_endpoint(prd_id: str, body: PrdStatusUpdate):
    """Approve, reject, or otherwise transition a PRD's status."""
    try:
        updated = set_prd_status(
            prd_id,
            body.status,
            reviewed_by=body.reviewed_by,
            review_comment=body.review_comment,
        )
        return updated
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=f"PRD not found: {error}") from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/{prd_id}/approvals", response_model=list[dict])
def get_prd_approval_history(prd_id: str):
    """Get the approval event history for a PRD."""
    try:
        return get_prd_approvals(prd_id)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=f"PRD not found: {error}") from error


# ---------------------------------------------------------------------------
# PRD Comment endpoints
# ---------------------------------------------------------------------------


@router.get("/{prd_id}/comments", summary="Get all comments for a PRD")
def get_prd_comments_endpoint(prd_id: str):
    """Return all top-level comments with nested replies, ordered by creation time."""
    try:
        return list_comments(prd_id)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post("/{prd_id}/comments", status_code=201, summary="Add a comment or reply on a PRD")
def create_prd_comment(prd_id: str, body: CreateCommentRequest):
    """Create a new comment (or reply when parent_id is set) on a PRD section."""
    try:
        return add_comment(
            prd_id,
            section_id=body.section_id,
            section_title=body.section_title,
            author=body.author,
            text=body.text,
            parent_id=body.parent_id,
        )
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.delete("/{prd_id}/comments/{comment_id}", status_code=204, summary="Delete a comment")
def delete_prd_comment(prd_id: str, comment_id: str):
    """Delete a comment by ID."""
    try:
        remove_comment(comment_id)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
