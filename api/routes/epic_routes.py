from typing import Any
import json

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from api.models import AgentRequest, AgentResponse, JiraEpicsResponse
from backlog_generation.jira_qa_workflow import run_jira_qa_workflow
from api.services.epic_service import generate_epics
from api.services.prd_service import extract_prds_as_documents

router = APIRouter(tags=["agent", "jira-epics"])


@router.get("/")
def greet():
    return "Hello Catalyst !"


@router.post("/agent", response_model=AgentResponse)
def run_agent(payload: AgentRequest):
    return AgentResponse(response=run_jira_qa_workflow(payload.message, payload.issue_id))


@router.post("/jira/epic", response_model=JiraEpicsResponse)
async def run_jira_epic_agent(
    prompt: str = Form(...),
    epic_count: int = Form(3),
    supporting_documents: list[UploadFile] | None = File(default=None),
    selected_prds: str | None = Form(default=None),
    selected_modernization_docs: str | None = Form(default=None),
    selected_design_artifacts: str | None = Form(default=None),
    selected_architecture_diagrams: str | None = Form(default=None),
):
    try:
        prd_documents = []
        prd_ids: list[str] = []
        modernization_doc_ids: list[str] = []
        design_artifact_ids: list[str] = []
        if selected_prds:
            try:
                parsed_ids = json.loads(selected_prds)
                if isinstance(parsed_ids, list):
                    prd_ids = [str(prd_id) for prd_id in parsed_ids]
                    prd_documents = extract_prds_as_documents(prd_ids)
            except json.JSONDecodeError:
                pass

        if selected_modernization_docs:
            try:
                parsed_modernization_ids = json.loads(selected_modernization_docs)
                if isinstance(parsed_modernization_ids, list):
                    modernization_doc_ids = [str(doc_id) for doc_id in parsed_modernization_ids]
            except json.JSONDecodeError:
                pass

        if selected_design_artifacts:
            try:
                parsed_design_artifact_ids = json.loads(selected_design_artifacts)
                if isinstance(parsed_design_artifact_ids, list):
                    design_artifact_ids = [str(artifact_id) for artifact_id in parsed_design_artifact_ids]
            except json.JSONDecodeError:
                pass

        # Backward compatibility with earlier payload field.
        if selected_architecture_diagrams:
            try:
                parsed_architecture_ids = json.loads(selected_architecture_diagrams)
                if isinstance(parsed_architecture_ids, list):
                    design_artifact_ids.extend([str(artifact_id) for artifact_id in parsed_architecture_ids])
            except json.JSONDecodeError:
                pass
        
        validated_epics, backlog_id = await generate_epics(
            prompt,
            supporting_documents,
            epic_count,
            prd_documents,
            prd_ids or None,
            modernization_doc_ids or None,
            design_artifact_ids or None,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"Epic generation failed: {error}") from error

    return JiraEpicsResponse(epics=validated_epics.epics, backlog_id=backlog_id)

