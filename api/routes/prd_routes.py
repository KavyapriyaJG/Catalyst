import asyncio
import json
import os
import queue as queue_module
import re

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from api.models import PrdGenerateRequest, PrdItem, PrdListItem
from dummy_prd_content import DUMMY_PRD_STREAM_EVENTS, DUMMY_PRD_TEXT
from prd_generation.prd_generation_graph import run_prd_pipeline
from api.services.prd_service import clone_repository, extract_and_validate_documents, get_prd, list_prds, save_prd

router = APIRouter(prefix="/prd", tags=["prd"])

def format_prd_keys(prd_dict: dict) -> dict:
    """Convert snake_case keys to Title Case with spaces."""
    return {key.replace('_', ' ').title(): value for key, value in prd_dict.items()}

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
    github_urls: list[str] | None,
    documents: list[dict],
):
    """Async generator that runs the PRD pipeline and yields SSE-formatted messages."""
    event_queue: queue_module.Queue[str] = queue_module.Queue()
    pipeline_task = asyncio.create_task(
        run_prd_pipeline(
            input_path=input_path,
            github_urls=github_urls,
            documents=documents,
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
        prd_text = pipeline_task.result()
        filename, prd_json = save_prd(prd_text)
        formatted_prd = format_prd_keys(prd_json)
        yield f"event: complete\ndata: {json.dumps({'prd': formatted_prd, 'file': filename})}\n\n"
    except Exception as error:
        yield f"event: error\ndata: {json.dumps({'error': str(error)})}\n\n"


@router.post("/generate")
async def generate_prd_sse(payload: PrdGenerateRequest):
    input_path, parsed_documents = _resolve_prd_inputs(payload)
    return StreamingResponse(
        _stream_prd_pipeline(input_path, payload.github_urls, parsed_documents),
        media_type="text/event-stream",
    )


@router.post("/generate/dummy")
async def generate_prd_sse_dummy(_payload: PrdGenerateRequest):
    """Dummy endpoint that replays the real /prd/generate SSE stream with artificial delays."""

    async def event_generator():
        for msg, delay in DUMMY_PRD_STREAM_EVENTS:
            yield f"data: {msg}\n\n"
            await asyncio.sleep(delay)

        prd_dict = json.loads(DUMMY_PRD_TEXT)
        filename, prd_json = save_prd(prd_dict)
        formatted_prd = format_prd_keys(prd_json)
        yield (
            f"event: complete\n"
            f"data: {json.dumps({'prd': formatted_prd, 'file': filename})}\n\n"
        )

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/list", response_model=list[PrdListItem])
def get_prds_list():
    return list_prds()


@router.get("/{filename}", response_model=PrdItem)
def get_prd_by_filename(filename: str):
    try:
        return get_prd(filename)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=f"PRD not found: {error}") from error
