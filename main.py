import asyncio
import json
import os
from pathlib import Path
import queue as queue_module
import re
import shutil
import urllib.error
import urllib.request
import uuid
from datetime import datetime
from typing import Literal
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from dummy_prd_content import DUMMY_PRD_STREAM_EVENTS, DUMMY_PRD_TEXT

from backlog_generation.epic_agent import (
    JiraEpicOutput,
    JiraEpicsOutput,
    JiraStoriesOutput,
    generate_jira_epics,
    generate_stories_from_epic,
)
from jira_utils import (
    build_jira_bulk_epics_payload,
    build_jira_bulk_story_payload,
    jira_auth_header,
    jira_bulk_endpoint,
)
from backlog_generation.simple_langgraph import run_simple_langgraph

# ────────────────────────────────────────────────────────────────
# Constants & Utilities
# ────────────────────────────────────────────────────────────────

app = FastAPI()

WORKSPACE_DIR = Path(__file__).parent / "workspace"
GENERATED_PRDS_DIR = Path(__file__).parent / "generated_prds"
UPLOADS_DIR = Path(__file__).parent / "uploads"

# Ensure directories exist on startup
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
GENERATED_PRDS_DIR.mkdir(parents=True, exist_ok=True)


def sanitize_filename(filename: str) -> str:
    """Remove/replace unsafe characters from filename"""
    # Keep only alphanumeric, dots, hyphens, underscores
    safe = re.sub(r'[^a-zA-Z0-9._-]', '_', filename)
    # Remove leading/trailing dots and slashes
    safe = safe.strip('._/\\')
    # Limit length to 255 chars (filesystem limit)
    safe = safe[:255]
    return safe or "file"

allowed_origins = [
    "http://localhost:8080",
    "http://127.0.0.1:8080",
    "http://localhost:8081",
    "http://127.0.0.1:8081",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AgentRequest(BaseModel):
    message: str
    issue_id: str


class AgentResponse(BaseModel):
    response: str


class JiraEpicsResponse(BaseModel):
    epics: list[JiraEpicOutput]


class JiraStoriesRequest(BaseModel):
    epic: JiraEpicOutput
    story_count: int = Field(default=5, ge=1, le=20)


class JiraStoriesResponse(BaseModel):
    stories: JiraStoriesOutput


class JiraBulkPublishResponse(BaseModel):
    issues: list[dict[str, Any]] = Field(default_factory=list)
    errors: list[Any] = Field(default_factory=list)


def generate_agent_response(message: str, issue_id: str) -> str:
    return run_simple_langgraph(message, issue_id)


@app.get("/")
def greet():
    return "Hello Catalyst !"


@app.post("/agent", response_model=AgentResponse)
def run_agent(payload: AgentRequest):
    return AgentResponse(response=generate_agent_response(payload.message, payload.issue_id))


@app.post("/jira/epic", response_model=JiraEpicsResponse)
async def run_jira_epic_agent(
    prompt: str = Form(...),
    epic_count: int = Form(3),
    supporting_documents: list[UploadFile] | None = File(default=None),
):
    try:
        cleaned_prompt = prompt.strip()
        if not cleaned_prompt:
            raise ValueError("Prompt cannot be empty.")

        parsed_documents: list[dict[str, str]] = []
        for file in (supporting_documents or []):
            raw_bytes = await file.read()
            if not raw_bytes:
                continue

            try:
                content = raw_bytes.decode("utf-8")
            except UnicodeDecodeError:
                content = raw_bytes.decode("latin-1", errors="ignore")

            parsed_documents.append(
                {
                    "filename": file.filename or "document.txt",
                    "content": content,
                }
            )

        epics_data: dict[str, Any] = generate_jira_epics(
            cleaned_prompt,
            parsed_documents,
            epic_count=epic_count,
        )
        validated_epics = JiraEpicsOutput(**epics_data)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"Epic generation failed: {error}") from error

    return JiraEpicsResponse(epics=validated_epics.epics)


@app.post("/jira/stories", response_model=JiraStoriesResponse)
def run_jira_story_agent(payload: JiraStoriesRequest):
    try:
        stories_data: dict[str, Any] = generate_stories_from_epic(
            payload.epic.model_dump(), payload.story_count
        )
        validated_stories = JiraStoriesOutput(**stories_data)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"Story generation failed: {error}") from error

    return JiraStoriesResponse(stories=validated_stories)


@app.post("/jira/publish/issues", response_model=JiraBulkPublishResponse)
def publish_issues_to_jira(
    payload: JiraEpicsResponse | JiraStoriesResponse,
    issue_type: Literal["epic", "story"] = Query(default="epic", alias="type"),
    parent_key: str | None = Query(default=None, alias="parent-key"),
):
    if issue_type == "story":
        if not isinstance(payload, JiraStoriesResponse):
            raise HTTPException(
                status_code=400,
                detail="For type=story, payload must include a `stories` object.",
            )
        if not payload.stories.stories:
            raise HTTPException(status_code=400, detail="`stories.stories` cannot be empty.")
    else:
        if not isinstance(payload, JiraEpicsResponse):
            raise HTTPException(
                status_code=400,
                detail="For type=epic, payload must include an `epics` array.",
            )
        if not payload.epics:
            raise HTTPException(status_code=400, detail="`epics` cannot be empty.")
    
    try:
        if issue_type == "story":
            jira_bulk_payload = build_jira_bulk_story_payload(
                payload.stories,
                parent_key=parent_key,
            )
        else:
            jira_bulk_payload = build_jira_bulk_epics_payload(payload.epics)
    except ValueError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error
    

    request = urllib.request.Request(
        jira_bulk_endpoint(),
        data=json.dumps(jira_bulk_payload).encode("utf-8"),
        headers={
            "Authorization": jira_auth_header(),
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            jira_response = json.loads(response.read().decode("utf-8"))
    except ValueError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error
    except urllib.error.HTTPError as error:
        error_body = error.read().decode("utf-8", errors="ignore")
        try:
            jira_error = json.loads(error_body) if error_body else {"message": error.reason}
        except json.JSONDecodeError:
            jira_error = {"message": error_body or str(error.reason)}
        raise HTTPException(status_code=error.code, detail=jira_error) from error
    except urllib.error.URLError as error:
        raise HTTPException(status_code=502, detail=f"Failed to reach Jira: {error.reason}") from error
    except json.JSONDecodeError as error:
        raise HTTPException(status_code=502, detail=f"Invalid JSON response from Jira: {error}") from error

    if not isinstance(jira_response, dict):
        raise HTTPException(status_code=502, detail="Unexpected Jira response format.")

    return JiraBulkPublishResponse(
        issues=jira_response.get("issues", []),
        errors=jira_response.get("errors", []),
    )


# =========================
# PRD GENERATION (SSE)
# =========================

from prd_generation.prd_generation_graph import run_prd_pipeline


class PrdGenerateRequest(BaseModel):
    input_path: str | None = None
    github_urls: list[str] | None = None
    documents: list[dict] | None = None


@app.post("/prd/generate")
async def generate_prd_sse(payload: PrdGenerateRequest):
    if not payload.input_path and not payload.github_urls and not payload.documents:
        raise HTTPException(
            status_code=400, detail="Provide either input_path, github_urls, or documents"
        )

    input_path = payload.input_path

    if payload.github_urls:
        if not payload.github_urls:
            raise HTTPException(
                status_code=400, detail="github_urls list cannot be empty"
            )
        url = payload.github_urls[0].strip()
        if not re.match(
            r"^https://[a-zA-Z0-9._-]+(/[a-zA-Z0-9._-]+)+(?:\.git)?$", url
        ):
            raise HTTPException(
                status_code=400, detail=f"Invalid GitHub URL format: {url}"
            )

        WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
        repo_name = url.rstrip("/").split("/")[-1].replace(".git", "")
        clone_dir = WORKSPACE_DIR / repo_name

        if clone_dir.exists():
            shutil.rmtree(clone_dir)

        try:
            import git
            git.Repo.clone_from(url, str(clone_dir))
        except git.GitCommandError as e:
            raise HTTPException(
                status_code=400,
                detail=f"Failed to clone repository: {e.stderr}",
            )

        input_path = str(clone_dir)

    if not os.path.isdir(input_path):
        raise HTTPException(
            status_code=400, detail=f"Path does not exist: {input_path}"
        )

    event_queue: queue_module.Queue[str] = queue_module.Queue()

    async def event_generator():
        pipeline_task = asyncio.create_task(
            run_prd_pipeline(input_path, event_queue)
        )

        while not pipeline_task.done():
            await asyncio.sleep(0.1)
            while not event_queue.empty():
                try:
                    msg = event_queue.get_nowait()
                    yield f"data: {msg}\n\n"
                except queue_module.Empty:
                    break

        # Drain remaining events
        while not event_queue.empty():
            try:
                msg = event_queue.get_nowait()
                yield f"data: {msg}\n\n"
            except queue_module.Empty:
                break

        # Emit final result or error
        try:
            prd_text = pipeline_task.result()

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            unique_id = uuid.uuid4().hex[:8]
            filename = f"prd_{timestamp}_{unique_id}.md"
            filepath = GENERATED_PRDS_DIR / filename
            filepath.write_text(prd_text)

            yield (
                f"event: complete\n"
                f"data: {json.dumps({'prd': prd_text, 'file': filename})}\n\n"
            )
        except Exception as e:
            yield (
                f"event: error\n"
                f"data: {json.dumps({'error': str(e)})}\n\n"
            )

    return StreamingResponse(
        event_generator(), media_type="text/event-stream"
    )


class PrdListItem(BaseModel):
    filename: str


class PrdItem(BaseModel):
    filename: str
    content: str


@app.get("/prd/list", response_model=list[PrdListItem])
def list_prds():
    return [
        PrdListItem(filename=filepath.name)
        for filepath in sorted(GENERATED_PRDS_DIR.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    ]


@app.get("/prd/{filename}", response_model=PrdItem)
def get_prd(filename: str):
    filepath = GENERATED_PRDS_DIR / filename
    if not filepath.exists() or filepath.suffix != ".md":
        raise HTTPException(status_code=404, detail=f"PRD not found: {filename}")
    return PrdItem(filename=filepath.name, content=filepath.read_text())


# =========================
# DUMMY PRD GENERATION (SSE) — no LLM calls, simulates real streaming
# =========================

@app.post("/prd/generate/dummy")
async def generate_prd_sse_dummy(_payload: PrdGenerateRequest):
    """Dummy endpoint that replays the real /prd/generate SSE stream with artificial delays."""

    async def event_generator():
        for msg, delay in DUMMY_PRD_STREAM_EVENTS:
            yield f"data: {msg}\n\n"
            await asyncio.sleep(delay)

        # ── Final: write file and emit complete event ──────────────────────
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_id = uuid.uuid4().hex[:8]
        filename = f"prd_{timestamp}_{unique_id}.md"
        filepath = GENERATED_PRDS_DIR / filename
        filepath.write_text(DUMMY_PRD_TEXT)

        yield (
            f"event: complete\n"
            f"data: {json.dumps({'prd': DUMMY_PRD_TEXT, 'file': filename})}\n\n"
        )

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# =========================
# FILE UPLOAD STORAGE — simple folder-based storage for uploaded documents
# =========================

MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50MB


@app.post("/files/upload")
async def upload_file(
    file: UploadFile = File(...),
    id: str = Form(...),
    name: str = Form(...),
):
    """Upload and store file in uploads folder with validation"""
    # Sanitize filename to prevent path traversal attacks
    safe_name = sanitize_filename(name)
    if not safe_name:
        raise HTTPException(status_code=400, detail="Invalid filename")
    
    # Validate file size
    contents = await file.read()
    if len(contents) > MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=413, detail=f"File too large. Max size is {MAX_UPLOAD_SIZE / 1024 / 1024:.0f}MB")
    
    # Save file
    filepath = UPLOADS_DIR / f"{id}_{safe_name}"
    filepath.write_bytes(contents)
    
    # Get upload timestamp
    uploaded_at = datetime.now().strftime("%m/%d/%Y, %I:%M:%S %p")
    
    return {"status": "ok", "id": id, "uploaded_at": uploaded_at}


class UploadedFileItem(BaseModel):
    id: str
    name: str
    size: str
    uploaded_at: str
    file: None = None


@app.get("/files/list", response_model=list[UploadedFileItem])
def list_uploaded_files():
    """Get list of all uploaded files"""
    files = []
    
    if not UPLOADS_DIR.exists():
        return files
    
    for filepath in sorted(UPLOADS_DIR.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if filepath.is_file():
            parts = filepath.name.split("_", 1)
            if len(parts) == 2:
                file_id = parts[0]
                original_name = parts[1]
                file_size = filepath.stat().st_size
                # Get upload time from file modification time
                mtime = datetime.fromtimestamp(filepath.stat().st_mtime)
                uploaded_at = mtime.strftime("%m/%d/%Y, %I:%M:%S %p")
                files.append(
                    UploadedFileItem(
                        id=file_id,
                        name=original_name,
                        size=f"{file_size / 1024:.1f} KB" if file_size > 0 else "0 KB",
                        uploaded_at=uploaded_at,
                    )
                )
    
    return files


@app.delete("/files/delete/{file_id}")
def delete_file(file_id: str):
    """Delete an uploaded file"""
    if not UPLOADS_DIR.exists():
        raise HTTPException(status_code=404, detail="File not found")
    
    for filepath in UPLOADS_DIR.iterdir():
        if filepath.name.startswith(f"{file_id}_"):
            filepath.unlink()
            return {"status": "deleted"}
    
    raise HTTPException(status_code=404, detail="File not found")
