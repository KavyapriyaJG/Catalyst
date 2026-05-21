from fastapi import APIRouter, HTTPException

from api.models import DesignArtifactDetail, DesignArtifactListItem, DesignGenerateRequest
from api.services.design_service import (
    SUPPORTED_DIAGRAM_TYPES,
    generate_design_artifacts,
    get_design_artifact,
    list_design_artifacts,
)

router = APIRouter(prefix="/design", tags=["design"])


@router.post("/generate")
async def generate_design(payload: DesignGenerateRequest):
    if payload.generate_all:
        diagram_types = list(SUPPORTED_DIAGRAM_TYPES)
    else:
        if not payload.diagram_type:
            raise HTTPException(status_code=400, detail="diagram_type is required when generate_all=false")
        diagram_types = [payload.diagram_type]

    try:
        artifacts = generate_design_artifacts(
            prd_id=payload.prd_id,
            artifact_name=payload.artifact_name,
            modernization_documents=payload.modernization_documents,
            context_artifact_ids=payload.context_artifact_ids,
            diagram_types=diagram_types,
        )
        return {
            "artifacts": artifacts,
            "count": len(artifacts),
            "generate_all": payload.generate_all,
        }
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=f"PRD not found: {error}") from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"Design generation failed: {error}") from error


@router.get("/list", response_model=list[DesignArtifactListItem])
def get_design_list():
    return list_design_artifacts()


@router.get("/{artifact_id}", response_model=DesignArtifactDetail)
def get_design_by_id(artifact_id: str):
    try:
        return get_design_artifact(artifact_id)
    except FileNotFoundError as error:
        raise HTTPException(status_code=404, detail=f"Design artifact not found: {error}") from error
