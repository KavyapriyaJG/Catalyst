import json
import urllib.error
import urllib.request
from typing import Literal
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

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

app = FastAPI()

allowed_origins = [
    "http://localhost:8080",
    "http://127.0.0.1:8080",
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
