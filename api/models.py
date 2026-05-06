from typing import Any

from pydantic import BaseModel, Field

from backlog_generation.epic_agent import JiraEpicOutput, JiraStoriesOutput


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


class PrdGenerateRequest(BaseModel):
    input_path: str | None = None
    github_urls: list[str] | None = None
    documents: list[dict] | None = None


class PrdListItem(BaseModel):
    filename: str


class PrdItem(BaseModel):
    filename: str
    content: dict
    generated_time: float


class UploadedFileItem(BaseModel):
    id: str
    name: str
    size: str
    uploaded_at: str
    file: None = None
