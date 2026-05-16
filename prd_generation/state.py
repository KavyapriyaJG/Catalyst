from typing import TypedDict, Dict, Any


class AgentState(TypedDict):
    # Input routing
    input_path: str | None
    github_urls: list[str] | None
    documents: list[dict] | None
    priority_mode: str
    code_priority: int
    docs_priority: int
    priority_reason: str

    # Analysis results
    code_analysis: str | None
    document_analysis: str | None
    analysis: Dict[str, Any]

    # PRD generation loop
    prd: Dict[str, Any]
    review: Dict[str, Any]
    score: float
    iteration: int
    best_prd: Dict[str, Any]
    best_score: float
