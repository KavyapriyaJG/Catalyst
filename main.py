from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from backlog_generation.epic_agent import (
    JiraEpicOutput,
    JiraEpicsOutput,
    JiraStoriesOutput,
    generate_jira_epics,
    generate_stories_from_epic,
)
from backlog_generation.simple_langgraph import run_simple_langgraph

app = FastAPI()


class AgentRequest(BaseModel):
    message: str
    issue_id: str


class AgentResponse(BaseModel):
    response: str


class JiraEpicResponse(BaseModel):
    epics: list[JiraEpicOutput]


class JiraStoriesRequest(BaseModel):
    epic: JiraEpicOutput
    story_count: int = Field(default=5, ge=1, le=20)


class JiraStoriesResponse(BaseModel):
    stories: JiraStoriesOutput


def generate_agent_response(message: str, issue_id: str) -> str:
    return run_simple_langgraph(message, issue_id)


@app.get("/")
def greet():
    return "Hello Catalyst !"


@app.post("/agent", response_model=AgentResponse)
def run_agent(payload: AgentRequest):
    return AgentResponse(response=generate_agent_response(payload.message, payload.issue_id))


@app.post("/jira/epic", response_model=JiraEpicResponse)
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

    return JiraEpicResponse(epics=validated_epics.epics)


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
