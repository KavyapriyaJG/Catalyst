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
    prioritize_code: bool = False
    prioritize_documents: bool = False


class PrdListItem(BaseModel):
    id: str
    prd_name: str
    filename: str
    status: str | None = "draft"
    created_at: str | None = None


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


class DesignGenerateRequest(BaseModel):
    prd_id: str
    artifact_name: str | None = None
    modernization_documents: list[dict] | None = None
    context_artifact_ids: list[str] | None = None
    generate_all: bool = False
    diagram_type: str | None = None


class DesignArtifactListItem(BaseModel):
    id: str
    group_id: str | None = None
    prd_id: str
    artifact_name: str
    diagram_type: str
    status: str
    created_at: str
    updated_at: str


class DesignArtifactDetail(BaseModel):
    id: str
    group_id: str | None = None
    prd_id: str
    artifact_name: str
    diagram_type: str
    status: str
    created_at: str
    updated_at: str
    content: str
    explanation: str
