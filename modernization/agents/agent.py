"""LangGraph agent for modernization document generation with Reviewer & Reconciler."""

import asyncio
import json
import queue as queue_module
import sys
import traceback
from typing import Any, Literal, Optional

from langchain_core.messages import HumanMessage
from langgraph.graph import START, END, StateGraph
from typing_extensions import TypedDict

from config import get_settings
from modernization.prompt import get_modernization_blueprint_prompt
from modernization.output_formatter import extract_json_from_response, validate_modernization_sections
from modernization.agents.reviewer import review_modernization_blueprint
from modernization.agents.reconciler import reconcile_modernization_blueprint
from backlog_generation.db import get_session
from prd_generation.prd_repository import get_prd


_EMPTY_BLUEPRINT = {}


def get_claude_client():
    """Initialize ChatAnthropic with Azure Anthropic credentials."""
    from langchain_anthropic import ChatAnthropic
    s = get_settings()
    return ChatAnthropic(
        model=s.AZURE_ANTHROPIC_DEPLOYMENT_NAME,
        anthropic_api_url=s.AZURE_ANTHROPIC_ENDPOINT,
        anthropic_api_key=s.AZURE_ANTHROPIC_API_KEY,
        timeout=s.LLM_TIMEOUT,
        max_retries=s.LLM_MAX_RETRIES,
    )


class _OutputCapture:
    """Capture stdout writes to a queue for SSE streaming."""

    def __init__(self, event_queue: queue_module.Queue, original):
        self._queue = event_queue
        self._original = original

    def write(self, text: str):
        self._original.write(text)
        for line in text.split("\n"):
            stripped = line.strip()
            if stripped:
                self._queue.put(stripped)

    def flush(self):
        self._original.flush()


class ModernizationState(TypedDict):
    """State for modernization blueprint generation, review, and reconciliation."""
    doc_id: str
    doc_name: str
    modernization_goals: Optional[str]
    linked_prds: list[str]
    source_assets: list[dict]
    messages: list
    analysis: dict[str, Any]  # Source analysis (legacy code, pain points, etc.)
    blueprint: dict[str, Any] | str  # Generated/reconciled blueprint
    review: Optional[dict[str, Any]]  # Review findings
    score: int  # Current review score (0-100)
    best_score: int  # Best score achieved so far
    best_blueprint: Optional[dict[str, Any] | str]  # Best blueprint achieved
    iteration: int  # Reconciliation iteration count


def generate_modernization_blueprint(state: ModernizationState) -> dict[str, Any]:
    """Generate complete modernization blueprint in a single unified call."""
    print("\n[Step 1/3] Generating Modernization Blueprint...")
    
    prd_data = []
    try:
        with get_session() as session:
            for prd_id in state.get('linked_prds', []):
                prd_record = get_prd(session, prd_id)
                if prd_record:
                    prd_data.append({
                        "name": prd_record.prd_name,
                        "content": prd_record.prd_content or {}
                    })
    except Exception as e:
        print(f"   Warning: Could not fetch PRD details: {e}")
    
    prd_context = ""
    prd_names = []
    if not prd_data:
        print("   Warning: No linked PRDs found")
        prd_context = "No PRD details available"
    else:
        for prd in prd_data:
            prd_names.append(prd['name'])
            prd_context += f"\n{'='*60}\nPRD: {prd['name']}\n{'='*60}\n"
            
            content = prd['content']
            if isinstance(content, dict):
                for section, value in content.items():
                    if value:
                        prd_context += f"\n{section}:\n{str(value)}\n"
            else:
                prd_context += str(content)
    
    client = get_claude_client()
    prompt_text = get_modernization_blueprint_prompt(
        prd_summary=prd_context,
        legacy_analysis=f"PRDs: {', '.join(prd_names)}" if prd_names else "No PRDs provided",
        backlog_context=f"Goals: {state.get('modernization_goals', 'Not specified')}",
    )
    
    try:
        message = client.invoke([HumanMessage(content=prompt_text)])
    except Exception as e:
        print(f"   Error: Claude invocation failed: {e}")
        state["blueprint"] = {}
        return state
    
    try:
        parsed = extract_json_from_response(message.content)
        validate_modernization_sections(parsed)
        state["blueprint"] = parsed
    except (ValueError, json.JSONDecodeError) as e:
        print(f"   JSON parsing error: {e}")
        state["blueprint"] = _EMPTY_BLUEPRINT
    
    return state



def should_continue_reviewing(state: ModernizationState) -> Literal["reconcile", "END"]:
    """Decide whether to continue reconciling or finish."""
    s = get_settings()
    if state["score"] >= s.MODERNIZATION_SCORE_THRESHOLD:
        return END
    if state["iteration"] >= s.MODERNIZATION_MAX_ITERATIONS:
        return END
    return "reconcile"


def build_modernization_agent():
    """Build the modernization document generation agent with reviewer and reconciler."""
    workflow = StateGraph(ModernizationState)
    
    workflow.add_node("generate", generate_modernization_blueprint)
    workflow.add_node("review", review_modernization_blueprint)
    workflow.add_node("reconcile", reconcile_modernization_blueprint)
    
    workflow.set_entry_point("generate")
    workflow.add_edge("generate", "review")
    workflow.add_conditional_edges(
        "review",
        should_continue_reviewing,
        {"reconcile": "reconcile", END: END}
    )
    workflow.add_edge("reconcile", "review")
    
    return workflow.compile()


async def generate_modernization_doc(
    doc_id: str,
    doc_name: str,
    modernization_goals: Optional[str] = None,
    linked_prds: Optional[list[str]] = None,
    source_assets: Optional[list[dict]] = None,
    analysis: Optional[dict[str, Any]] = None,
    event_queue: Optional[queue_module.Queue] = None,
) -> dict[str, Any]:
    """
    Generate modernization blueprint asynchronously with review and reconciliation.
    
    Args:
        doc_id: Document ID
        doc_name: Document name
        modernization_goals: Optional modernization goals
        linked_prds: List of linked PRD IDs
        source_assets: List of uploaded supporting documents
        analysis: Source analysis (legacy code insights, pain points)
        event_queue: Optional queue for SSE streaming
    
    Returns:
        Dictionary containing:
        - blueprint: Final modernization blueprint
        - score: Final review score
        - best_score: Best score achieved across iterations
        - review: Final review findings
    """
    def _generate_sync():
        """Blocking generation wrapped for async execution."""
        if event_queue:
            original_stdout = sys.stdout
            sys.stdout = _OutputCapture(event_queue, original_stdout)
        
        try:
            result = build_modernization_agent().invoke(
                ModernizationState(
                    doc_id=doc_id,
                    doc_name=doc_name,
                    modernization_goals=modernization_goals,
                    linked_prds=linked_prds or [],
                    source_assets=source_assets or [],
                    messages=[],
                    analysis=analysis or {},
                    blueprint={},
                    review=None,
                    score=0,
                    best_score=0,
                    best_blueprint=None,
                    iteration=0,
                )
            )
            
            if result["score"] >= 80:
                blueprint = result["blueprint"]
            elif result.get("best_blueprint") and result.get("best_score", 0) > 0:
                blueprint = result["best_blueprint"]
            else:
                blueprint = result["blueprint"]
            
            return {
                "blueprint": blueprint,
                "score": result.get("score", 0),
                "best_score": result.get("best_score", 0),
            }
        finally:
            if event_queue:
                sys.stdout = original_stdout
    
    return await asyncio.to_thread(_generate_sync)
