import logging
from typing import Dict, Any
import queue as queue_module
import sys

from langgraph.graph import END, StateGraph

from config import get_settings
from prd_generation.agents.code_analysis import analyze
from prd_generation.agents.document_analysis import analyze_documents
from prd_generation.agents.prd_generator import generate_prd
from prd_generation.agents.reconciler import reconcile
from prd_generation.agents.reviewer import review_prd
from prd_generation.state import AgentState


# =========================
# MERGE + ROUTING NODES
# =========================

def merge_analysis(s: AgentState):
    """Merge code and document analyses into a single analysis dict."""
    print("\n[Step 1.5/4] Merging analyses...")
    code_analysis = s.get("code_analysis")
    doc_analysis = s.get("document_analysis")

    if code_analysis and doc_analysis:
        merged = {
            "source": "code_and_documents",
            "code_insights": code_analysis[:500] + "..." if len(code_analysis) > 500 else code_analysis,
            "document_insights": doc_analysis[:500] + "..." if len(doc_analysis) > 500 else doc_analysis,
            "full_code_analysis": code_analysis,
            "full_document_analysis": doc_analysis,
        }
        print("   Merged both analyses (source: code_and_documents)")
        return {"analysis": merged}
    elif code_analysis:
        print("   Using code analysis only (source: code_only)")
        return {"analysis": {"source": "code_only", "analysis": code_analysis}}
    elif doc_analysis:
        print("   Using document analysis only (source: documents_only)")
        return {"analysis": {"source": "documents_only", "analysis": doc_analysis}}
    else:
        print("   No analysis available")
        return {"analysis": {"source": "none", "message": "No analysis available"}}



# =========================
# GRAPH
# =========================

graph = StateGraph(AgentState)


def route_entry(s):
    """Route entry point based on input type."""
    has_code = bool(s.get('input_path') or s.get('github_urls'))
    has_docs = bool(s.get('documents'))
    
    if has_code and has_docs:
        return "both"
    elif has_code:
        return "code"
    elif has_docs:
        return "docs"
    return "error"


def route_after_code(s: AgentState):
    return "docs" if s.get("documents") else "merge"


def route_start_node(s: AgentState):
    return {}


def should_continue(state: AgentState):
    s = get_settings()
    if state["score"] >= s.PRD_SCORE_THRESHOLD:
        print(f"\nDone (score >= {s.PRD_SCORE_THRESHOLD}). Final score: {state['score']}/100")
        return END
    if state["iteration"] >= s.PRD_MAX_ITERATIONS:
        best = state.get("best_score", state["score"])
        print(f"\nDone (max iterations reached). Using best PRD with score: {best}/100")
        return END
    print(f"   Score {state['score']}/100 < {s.PRD_SCORE_THRESHOLD}, refining...")
    return "reconcile"


# =========================
# GRAPH
# =========================

graph = StateGraph(AgentState)
graph.add_node("_route_start", route_start_node)
graph.add_node("analyze_code", analyze)
graph.add_node("analyze_documents", analyze_documents)
graph.add_node("merge", merge_analysis)
graph.add_node("prd", generate_prd)
graph.add_node("review", review_prd)
graph.add_node("reconcile", reconcile)

graph.set_entry_point("_route_start")
graph.add_conditional_edges(
    "_route_start",
    route_entry,
    {"code": "analyze_code", "docs": "analyze_documents", "both": "analyze_code"},
)
graph.add_conditional_edges(
    "analyze_code",
    route_after_code,
    {"docs": "analyze_documents", "merge": "merge"},
)
graph.add_edge("analyze_documents", "merge")
graph.add_edge("merge", "prd")
graph.add_edge("prd", "review")
graph.add_conditional_edges("review", should_continue)
graph.add_edge("reconcile", "review")

prd_pipeline = graph.compile()


# =========================
# SSE OUTPUT CAPTURE
# =========================

_MODEL_URL_MAP = {
    "gitnexus-test.openai.azure.com": "Codex (gpt-5.3-codex)",
    "kavin-mnh5g313-eastus2.services.ai.azure.com": "Claude (claude-opus-4-7)",
}


class _OutputCapture:
    """Tee stdout writes to a thread-safe queue for SSE streaming."""

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


class _QueueLogHandler(logging.Handler):
    """Push httpx log records to the SSE queue, replacing raw URLs with model names."""

    def __init__(self, event_queue: queue_module.Queue):
        super().__init__()
        self._queue = event_queue

    def emit(self, record):
        msg = self.format(record)
        if not msg.strip():
            return
        for url_fragment, model_label in _MODEL_URL_MAP.items():
            if url_fragment in msg:
                self._queue.put(f"   {model_label} API call completed")
                return


# =========================
# PIPELINE ENTRY POINT
# =========================

async def run_prd_pipeline(
    input_path: str = None,
    github_urls: list = None,
    documents: list = None,
    event_queue: queue_module.Queue = None
) -> Dict[str, Any]:
    """Run the PRD pipeline with code, documents, or both inputs.
    
    Args:
        input_path: Local directory path for code analysis
        github_urls: List of GitHub URLs for code analysis
        documents: List of uploaded documents [{id, name, file_content}, ...]
        event_queue: Queue for SSE streaming of progress messages
    """
    original_stdout = sys.stdout
    if event_queue:
        sys.stdout = _OutputCapture(event_queue, original_stdout)

    log_handler = _QueueLogHandler(event_queue) if event_queue else None
    if log_handler:
        log_handler.setFormatter(logging.Formatter("%(message)s"))
        logging.getLogger("httpx").addHandler(log_handler)

    try:
        initial_state = {
            "input_path": input_path,
            "github_urls": github_urls or [],
            "documents": documents or [],
            "code_analysis": None,
            "document_analysis": None,
            "analysis": {},
            "prd": {},
            "review": {},
            "score": 0,
            "iteration": 0,
            "best_prd": {},
            "best_score": 0,
        }

        result = await prd_pipeline.ainvoke(initial_state)

        if result["score"] >= 80:
            prd_json = result["prd"]
            print(f"\n   Using current PRD (score: {result['score']}/100)")
        else:
            best_prd = result.get("best_prd", {})
            if best_prd and result.get("best_score", 0) > result["score"]:
                prd_json = best_prd
                print(
                    f"\n   Using best PRD from earlier iteration "
                    f"(score: {result['best_score']}/100 vs final: {result['score']}/100)"
                )
            else:
                prd_json = result["prd"]
                print(f"\n   Using final PRD (score: {result['score']}/100)")

        return prd_json
    finally:
        if event_queue:
            sys.stdout = original_stdout
        if log_handler:
            logging.getLogger("httpx").removeHandler(log_handler)
