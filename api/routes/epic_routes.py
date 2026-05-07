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
):
    try:
        prd_documents = []
        if selected_prds:
            try:
                prd_ids = json.loads(selected_prds)
                if isinstance(prd_ids, list):
                    prd_documents = extract_prds_as_documents(prd_ids)
            except json.JSONDecodeError:
                pass
        
        validated_epics, backlog_id = await generate_epics(
            prompt, supporting_documents, epic_count, prd_documents
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"Epic generation failed: {error}") from error

    return JiraEpicsResponse(epics=validated_epics.epics, backlog_id=backlog_id)

