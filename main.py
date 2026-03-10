from fastapi import FastAPI
from pydantic import BaseModel

from backlog_generation.simple_langgraph import run_simple_langgraph

app = FastAPI()


class AgentRequest(BaseModel):
    message: str
    issue_id: str


class AgentResponse(BaseModel):
    response: str


def generate_agent_response(message: str, issue_id: str) -> str:
    return run_simple_langgraph(message, issue_id)

@app.get("/")
def greet():
    return "Hello Catalyst !"


@app.post("/agent", response_model=AgentResponse)
def run_agent(payload: AgentRequest):
    return AgentResponse(response=generate_agent_response(payload.message, payload.issue_id))
