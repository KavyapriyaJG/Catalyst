"""Pydantic models for modernization API requests and responses."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class SourceAsset(BaseModel):
    """Metadata for an uploaded supporting document."""
    filename: str
    path: str
    uploaded_at: str
    size: int = 0


class LinkedPrd(BaseModel):
    """Linked PRD with name."""
    id: str
    prd_name: str


class ModernizationDocResponse(BaseModel):
    """Response model for modernization document details."""
    id: str
    name: str
    description: Optional[str] = None
    status: str
    modernization_goals: Optional[str] = None
    linked_prds: list[LinkedPrd]
    source_assets: list[SourceAsset]
    generated_sections: dict = {}
    created_at: datetime
    updated_at: datetime
    submitted_at: Optional[datetime] = None
    submitted_by: Optional[str] = None
    reviewed_by: Optional[str] = None
    review_comment: Optional[str] = None


class ModernizationDocListItem(BaseModel):
    """List view of modernization document."""
    id: str
    name: str
    description: Optional[str] = None
    status: str
    created_at: datetime
    updated_at: datetime
    submitted_by: Optional[str] = None
    reviewed_by: Optional[str] = None


class CreateModernizationRequest(BaseModel):
    """Request to create a new modernization document."""
    name: str = Field(..., min_length=1, max_length=500, description="Name of modernization document")
    modernization_goals: Optional[str] = Field(None, min_length=0, max_length=2000, description="Optional user input on modernization strategy/goals - AI will analyze documents if not provided")
    linked_prds: list[str] = Field(default_factory=list, description="List of linked PRD IDs")
    description: Optional[str] = None


class UpdateModernizationRequest(BaseModel):
    """Request to update a modernization document (save draft)."""
    name: Optional[str] = None
    description: Optional[str] = None
    modernization_goals: Optional[str] = None
    linked_prds: Optional[list[str]] = None


class SubmitForApprovalRequest(BaseModel):
    """Request to submit modernization doc for approval."""
    submitted_by: str = Field(..., description="Email or username of submitter")
    comment: Optional[str] = None


class ApprovalActionRequest(BaseModel):
    """Request to approve or reject a modernization document."""
    action: str = Field(..., description="'approve' or 'reject'")
    reviewed_by: str = Field(..., description="Email or username of reviewer")
    comment: str = Field(..., description="Approval or rejection comment")


class ExportDocxRequest(BaseModel):
    """Request to export modernization doc as DOCX."""
    include_generated_sections: bool = True


class FileUploadResponse(BaseModel):
    """Response for file upload."""
    filename: str
    path: str
    size: int
    uploaded_at: str


class ModernizationGenerationRequest(BaseModel):
    """Request for auto-generating modernization doc from PRDs."""
    name: str
    linked_prd_ids: list[str]
    custom_goals: Optional[str] = None
