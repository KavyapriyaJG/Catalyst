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
    backlog_id: str | None = None


class JiraStoriesRequest(BaseModel):
    epic: JiraEpicOutput
    story_count: int = Field(default=5, ge=1, le=20)
    backlog_id: str | None = None
    epic_record_id: str | None = None


class JiraStoriesResponse(BaseModel):
    stories: JiraStoriesOutput


class JiraBulkPublishResponse(BaseModel):
    issues: list[dict[str, Any]] = Field(default_factory=list)
    errors: list[Any] = Field(default_factory=list)


class PrdGenerateRequest(BaseModel):
    prd_name: str | None = None
    input_path: str | None = None
    github_urls: list[str] | None = None
    documents: list[dict] | None = None


class PrdListItem(BaseModel):
    id: str
    prd_name: str
    filename: str
    status: str | None = "draft"


class PrdItem(BaseModel):
    id: str
    prd_name: str
    filename: str
    content: dict
    generated_time: float
    status: str | None = "draft"
    reviewed_by: str | None = None
    review_comment: str | None = None
    reviewed_at: str | None = None


class PrdStatusUpdate(BaseModel):
    status: str
    reviewed_by: str | None = None
    review_comment: str | None = None


class UploadedFileItem(BaseModel):
    id: str
    name: str
    size: str
    uploaded_at: str
    file: None = None
