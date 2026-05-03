import asyncio
from typing import TypedDict, Dict, Any
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from deepagents import create_deep_agent
from langchain.tools import tool
from langchain_anthropic import ChatAnthropic
from prd_generation.prompts import (
    ANALYSIS_AGENT_PROMPT,
    COBOL_PRD_GENERATOR_PROMPT,
    DOCUMENT_PRD_GENERATOR_PROMPT,
    COMBINED_PRD_GENERATOR_PROMPT,
    REVIEWER_PROMPT,
    RECONCILER_PROMPT
)

import os
import re
import sys
import json
import time
import queue as queue_module
import logging
from dotenv import load_dotenv
from utils.document_utils import build_documents, retrieve_context

load_dotenv()

# Minimal logging — only show HTTP request URLs (not full payloads)
logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s %(message)s",
    datefmt="%H:%M:%S"
)
# Show only HTTP request/response timing
logging.getLogger("httpx").setLevel(logging.INFO)

def extract_text(content) -> str:
    """Extract plain text from LLM content (handles both str and list of blocks)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and "text" in block:
                parts.append(block["text"])
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts)
    return str(content)

# =========================
# STATE
# =========================

class AgentState(TypedDict):
    # Input routing
    input_path: str | None  # For code analysis
    github_urls: list[str] | None  # For code from GitHub
    documents: list[dict] | None  # For document analysis
    
    # Analysis results
    code_analysis: str | None  # Raw code analysis
    document_analysis: str | None  # Raw document analysis
    analysis: Dict[str, Any]  # Merged analysis (code + documents)
    
    # PRD generation loop
    prd: str
    review: Dict[str, Any]
    score: float
    iteration: int
    best_prd: str
    best_score: float

# =========================
# LLM
# =========================

llm_codex = ChatOpenAI(
    model=os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-5.3-codex"),
    base_url=os.getenv("AZURE_OPENAI_ENDPOINT"),
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
    timeout=600,
    max_retries=2,
    temperature=0
)

llm_claude = ChatAnthropic(
    model=os.getenv("AZURE_ANTHROPIC_DEPLOYMENT_NAME", "claude-opus-4-7"),
    anthropic_api_url=os.getenv("AZURE_ANTHROPIC_ENDPOINT"),
    anthropic_api_key=os.getenv("AZURE_ANTHROPIC_API_KEY"),
    timeout=600,
    max_retries=2
)


# =========================
# PRE-READ SOURCE REGISTRY
# =========================

# Global registry of pre-read source files grouped by module
_module_registry: Dict[str, str] = {}
_module_summary: Dict[str, Dict] = {}


def _build_module_registry(input_path: str):
    """Pre-read all COBOL files and group by top-level module directory."""
    global _module_registry, _module_summary

    cobol_extensions = {'.cob', '.cbl', '.cpy'}
    other_names = {'Makefile', 'Dockerfile'}
    module_files: Dict[str, list] = {}

    for root, dirs, files in os.walk(input_path):
        dirs[:] = [d for d in dirs if d not in ('.git', '.github', 'node_modules')]
        for f in sorted(files):
            full = os.path.join(root, f)
            is_cobol = any(f.endswith(ext) for ext in cobol_extensions)
            is_other = f in other_names or f.lower().endswith('.md')
            if not (is_cobol or is_other):
                continue

            rel = os.path.relpath(full, input_path)
            parts = rel.split(os.sep)
            # Group: use 2-level depth (e.g. src/packets) for finer splitting
            if len(parts) >= 3:
                module = f"{parts[0]}/{parts[1]}"
            elif len(parts) == 2:
                module = parts[0]
            else:
                module = "root"
            module_files.setdefault(module, []).append(full)

    total_files = 0
    total_chars = 0
    errors = []
    for module, fpaths in module_files.items():
        bundle = []
        for fpath in fpaths:
            try:
                with open(fpath, "r", errors="replace") as fh:
                    content = fh.read()
                rel = os.path.relpath(fpath, input_path)
                bundle.append(f"=== FILE: {rel} ===\n{content}")
                total_files += 1
                total_chars += len(content)
            except Exception as e:
                errors.append(f"{fpath}: {e}")
        _module_registry[module] = "\n\n".join(bundle)
        _module_summary[module] = {"files": len(fpaths), "chars": len(_module_registry[module])}

    print(f"   Found {total_files} files in {len(_module_registry)} modules ({total_chars} chars total)")
    if errors:
        print(f"   ⚠️  {len(errors)} files failed to read")
    for mod, info in sorted(_module_summary.items()):
        print(f"     📁 {mod}: {info['files']} files, {info['chars']} chars")


@tool
def list_modules() -> dict:
    """List all available source code modules and their file counts.
    Returns a dict of module_name -> {files: N, chars: N}.
    Call this FIRST to see what modules are available for analysis."""
    print(f"   [TOOL] list_modules() called — {len(_module_summary)} modules available")
    return _module_summary


@tool
def get_module_source(module_name: str) -> str:
    """Get the full source code for a specific module.
    The module_name must match one returned by list_modules().
    Returns all COBOL/copybook file contents concatenated with file path headers."""
    if module_name not in _module_registry:
        print(f"   [TOOL] get_module_source('{module_name}') — NOT FOUND")
        return f"ERROR: Module '{module_name}' not found. Available: {list(_module_registry.keys())}"
    chars = len(_module_registry[module_name])
    print(f"   [TOOL] get_module_source('{module_name}') — returning {chars} chars")
    return _module_registry[module_name]


# =========================
# ANALYSIS AGENT (Codex for code analysis)
# =========================

analysis_agent = create_deep_agent(
    model=llm_codex,
    tools=[list_modules, get_module_source],
    system_prompt=ANALYSIS_AGENT_PROMPT
)

# =========================
# ANALYZE CODE (COBOL - PRESERVED)
# =========================

def analyze(s: AgentState):
    """COBOL-specific code analysis with module registry and parallel subagents.
    This function was created through multiple iterations and should not be generalized."""
    print("\n🔎 [Step 1/4] Analyzing COBOL source files...")
    input_path = s['input_path']

    # Step 1: Pre-read all files and group by module
    _build_module_registry(input_path)

    # Step 2: Let the deep agent analyze using task tool for subagent delegation
    modules_list = "\n".join(f"  - {m} ({info['files']} files, {info['chars']} chars)" for m, info in sorted(_module_summary.items()))
    print(f"   Invoking analysis agent (Codex) with {len(_module_summary)} modules...")
    t0 = time.time()
    result = analysis_agent.invoke({
        "messages": [{"role": "user", "content": (
            f"Analyze the COBOL codebase at {input_path}.\n\n"
            f"Available modules (pre-loaded):\n{modules_list}\n\n"
            f"CRITICAL — LAUNCH ALL SUBAGENTS IN PARALLEL:\n"
            f"1. Call list_modules() to confirm the module list.\n"
            f"2. Then in ONE SINGLE RESPONSE, emit ALL task tool calls at once — one per module.\n"
            f"   This makes them run concurrently. Do NOT call them one at a time.\n"
            f"   Each task instruction: 'Analyze module <name>. Call get_module_source(\"<name>\") to get source. "
            f"   Extract PROGRAM-IDs, DATA DIVISION, PROCEDURE DIVISION, dependencies, business rules. Return JSON.'\n"
            f"3. After all tasks complete, merge results into the final JSON output.\n"
            f"4. Do NOT skip any module."
        )}]
    })
    elapsed = time.time() - t0
    print(f"   Analysis agent completed in {int(elapsed)}s")

    # Extract subagent task results from message history
    if isinstance(result, dict):
        messages = result.get("messages", [])
        print(f"   Analysis complete. {len(messages)} messages exchanged.")

        # Extract subagent results from ToolMessages
        subagent_results = []
        for msg in messages:
            if getattr(msg, 'type', None) == 'tool' and getattr(msg, 'name', None) == 'task':
                content = extract_text(getattr(msg, 'content', ''))
                if content and len(content) > 50:
                    subagent_results.append(content)

        # Get LLM's final merged summary
        llm_summary = ""
        if messages:
            last_msg = messages[-1]
            content = getattr(last_msg, 'content', str(last_msg))
            llm_summary = extract_text(content)

        subagent_total = sum(len(r) for r in subagent_results)
        print(f"   Subagent results: {len(subagent_results)} modules, {subagent_total} chars total")
        print(f"   LLM summary: {len(llm_summary)} chars")

        if subagent_results:
            combined = (
                "=== ANALYSIS SUMMARY ===\n"
                f"{llm_summary}\n\n"
                "=== DETAILED MODULE ANALYSES ===\n\n"
                + "\n\n---\n\n".join(subagent_results)
            )
            print(f"   Combined analysis output: {len(combined)} chars")
            return {"code_analysis": combined}
        else:
            print(f"   WARNING: No subagent results found, using LLM summary only ({len(llm_summary)} chars)")
            return {"code_analysis": llm_summary}

    return {"code_analysis": str(result)}

# =========================
# ANALYZE DOCUMENTS (NEW)
# =========================

def analyze_documents(s: AgentState):
    """Document analysis using shared utilities - semantic search and context retrieval."""
    print("\n📄 [Step 1/4] Analyzing uploaded documents...")
    documents = s.get('documents', [])
    
    if not documents:
        print("   ⚠️  No documents provided")
        return {"document_analysis": "No documents uploaded."}

    try:
        # Build document objects from uploaded files
        doc_objects = build_documents(documents)
        print(f"   Built {len(doc_objects)} document objects")

        # Semantic search with multiple queries to extract insights
        queries = [
            "What are the main requirements and functional specifications?",
            "What are the key processes and workflows described?",
            "What data structures and entities are mentioned?",
            "What are the business rules and constraints?",
            "What are the technical specifications and dependencies?",
            "What are the integration points and external systems?"
        ]

        insights = []
        for q in queries:
            try:
                context = retrieve_context(q, doc_objects, top_k=6)
                if context:
                    insights.append(f"**{q}**\n{context}")
            except Exception as e:
                print(f"   ⚠️  Query '{q}' failed: {e}")

        doc_analysis = "\n\n---\n\n".join(insights) if insights else "Unable to extract meaningful insights from documents."
        print(f"   Document analysis complete ({len(doc_analysis)} chars)")
        return {"document_analysis": doc_analysis}

    except Exception as e:
        print(f"   ❌ Error during document analysis: {e}")
        return {"document_analysis": f"Error analyzing documents: {e}"}

# =========================
# MERGE ANALYSIS (NEW)
# =========================

def merge_analysis(s: AgentState):
    """Merge code and document analyses intelligently for combined flow."""
    print("\n🔗 [Step 1.5/4] Merging analyses...")
    
    code_analysis = s.get('code_analysis')
    doc_analysis = s.get('document_analysis')

    if code_analysis and doc_analysis:
        # Both present - intelligent merge
        merged = {
            "source": "code_and_documents",
            "code_insights": code_analysis[:500] + "..." if len(code_analysis) > 500 else code_analysis,
            "document_insights": doc_analysis[:500] + "..." if len(doc_analysis) > 500 else doc_analysis,
            "full_code_analysis": code_analysis,
            "full_document_analysis": doc_analysis
        }
        print(f"   ✅ Merged both analyses (source: code_and_documents)")
        return {"analysis": merged}
    elif code_analysis:
        # Code only
        merged = {
            "source": "code_only",
            "analysis": code_analysis
        }
        print(f"   ✅ Using code analysis only (source: code_only)")
        return {"analysis": merged}
    elif doc_analysis:
        # Documents only
        merged = {
            "source": "documents_only",
            "analysis": doc_analysis
        }
        print(f"   ✅ Using document analysis only (source: documents_only)")
        return {"analysis": merged}
    else:
        print(f"   ⚠️  No analysis available")
        return {"analysis": {"source": "none", "message": "No analysis available"}}

# =========================
# FIXED PRD GENERATOR
# =========================

def generate_prd(state: AgentState):
    print("\n📝 [Step 2/4] Generating PRD from analysis...")
    print(f"   Invoking Codex {os.getenv('AZURE_OPENAI_DEPLOYMENT_NAME', 'gpt-5.3-codex')} for PRD generation...")
    
    # Select appropriate prompt based on analysis source
    analysis_dict = state.get('analysis', {})
    source = analysis_dict.get('source') if isinstance(analysis_dict, dict) else None
    
    if source == 'code_only':
        prompt_template = COBOL_PRD_GENERATOR_PROMPT
        print(f"   Using COBOL-specific PRD generator (code-only flow)")
    elif source == 'documents_only':
        prompt_template = DOCUMENT_PRD_GENERATOR_PROMPT
        print(f"   Using document-specific PRD generator (documents-only flow)")
    elif source == 'code_and_documents':
        prompt_template = COMBINED_PRD_GENERATOR_PROMPT
        print(f"   Using combined PRD generator (code + documents flow)")
    else:
        raise ValueError(f"Unknown analysis source: {source}. Expected 'code_only', 'documents_only', or 'code_and_documents'")
    
    prompt = prompt_template.format(analysis=state['analysis'])
    t0 = time.time()
    result = llm_codex.invoke(prompt)
    elapsed = time.time() - t0
    prd_text = extract_text(result.content)
    print(f"   Codex responded in {int(elapsed)}s — PRD generated ({len(prd_text)} chars)")
    return {"prd": prd_text}

# =========================
# REVIEWER (STRICT JSON)
# =========================

def review_prd(state: AgentState):
    print(f"\n🔍 [Step 3/4] Reviewing PRD (iteration {state.get('iteration', 0) + 1})...")
    print(f"   Invoking Claude {os.getenv('AZURE_ANTHROPIC_DEPLOYMENT_NAME', 'claude-opus-4-7')} for PRD review...")
    prompt = REVIEWER_PROMPT.format(
        analysis=json.dumps(state['analysis'], indent=2) if isinstance(state['analysis'], dict) else str(state['analysis']),
        prd=state['prd']
    )
    t0 = time.time()
    result = llm_claude.invoke(prompt)
    elapsed = time.time() - t0
    print(f"   Claude responded in {int(elapsed)}s")
    raw = extract_text(result.content)

    # Strip markdown code fences if present (```json ... ``` or ``` ... ```)
    stripped = raw.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        # Remove opening fence (```json or ```)
        lines = lines[1:]
        # Remove closing fence
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()

    # Extract first {...} JSON object if there's leading/trailing text
    json_match = re.search(r'\{.*\}', stripped, re.DOTALL)
    if json_match:
        stripped = json_match.group(0)

    try:
        parsed = json.loads(stripped)
    except Exception as parse_err:
        print(f"   WARNING: Failed to parse review JSON: {parse_err}")
        print(f"   Raw response (first 500 chars): {raw[:500]}")
        parsed = {
            "score": 0,
            "issues": {"critical": ["Invalid JSON"], "moderate": [], "minor": []}
        }

    score = parsed.get("score", 0)
    grade = parsed.get("grade", "N/A")
    print(f"   Review score: {score}/100 (Grade: {grade})")

    # Track best-scoring PRD across iterations
    update = {
        "review": parsed,
        "score": score
    }
    prev_best = state.get("best_score", 0)
    if score > prev_best:
        print(f"   New best score: {score} (previous best: {prev_best})")
        update["best_prd"] = state["prd"]
        update["best_score"] = score
    return update

# =========================
# RECONCILER
# =========================

def reconcile(state: AgentState):
    print(f"\n🔧 [Step 4/4] Reconciling PRD (iteration {state['iteration'] + 1})...")
    print(f"   Invoking Codex {os.getenv('AZURE_OPENAI_DEPLOYMENT_NAME', 'gpt-5.3-codex')} for PRD reconciliation...")
    analysis_str = json.dumps(state['analysis'], indent=2) if isinstance(state['analysis'], dict) else str(state['analysis'])
    prompt = RECONCILER_PROMPT.format(
        prd=state['prd'],
        review=json.dumps(state['review'], indent=2),
        analysis=analysis_str
    )
    t0 = time.time()
    result = llm_codex.invoke(prompt)
    elapsed = time.time() - t0
    prd_text = extract_text(result.content)
    print(f"   Codex responded in {int(elapsed)}s — Reconciled PRD ({len(prd_text)} chars)")
    return {
        "prd": prd_text,
        "iteration": state["iteration"] + 1
    }

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
    else:
        return "error"


def route_after_code(s):
    """After code analysis, check if documents also need analysis."""
    if s.get('documents'):
        return "docs"
    else:
        return "merge"


def route_start_node(s):
    """Entry point that just passes through - routing happens via conditional edges."""
    return {}


graph.add_node("_route_start", route_start_node)
graph.add_node("analyze_code", analyze)
graph.add_node("analyze_documents", analyze_documents)
graph.add_node("merge", merge_analysis)
graph.add_node("prd", generate_prd)
graph.add_node("review", review_prd)
graph.add_node("reconcile", reconcile)

# Entry: route to code, docs, or both
graph.set_entry_point("_route_start")
graph.add_conditional_edges(
    "_route_start",
    route_entry,
    {
        "code": "analyze_code",
        "docs": "analyze_documents",
        "both": "analyze_code",
    }
)

# After code analysis: route to docs (if present) or merge
graph.add_conditional_edges(
    "analyze_code",
    route_after_code,
    {
        "docs": "analyze_documents",
        "merge": "merge"
    }
)

# After docs analysis: always merge
graph.add_edge("analyze_documents", "merge")

# After merge: generate PRD
graph.add_edge("merge", "prd")
graph.add_edge("prd", "review")

# =========================
# LOOP CONTROL
# =========================

def should_continue(state: AgentState):
    if state["score"] >= 80:
        print(f"\n✅ Done (score >= 80). Final score: {state['score']}/100")
        return END
    if state["iteration"] >= 4:
        best = state.get('best_score', state['score'])
        print(f"\n✅ Done (max iterations reached). Using best PRD with score: {best}/100")
        return END
    print(f"   Score {state['score']}/100 < 80, refining...")
    return "reconcile"

graph.add_conditional_edges("review", should_continue)
graph.add_edge("reconcile", "review")

prd_pipeline = graph.compile()


# =========================
# SSE OUTPUT CAPTURE
# =========================

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


_MODEL_URL_MAP = {
    "gitnexus-test.openai.azure.com": "Codex (gpt-5.3-codex)",
    "kavin-mnh5g313-eastus2.services.ai.azure.com": "Claude (claude-opus-4-7)",
}


class _QueueLogHandler(logging.Handler):
    """Push httpx log records to a queue, replacing raw URLs with model names."""
    def __init__(self, event_queue: queue_module.Queue):
        super().__init__()
        self._queue = event_queue

    def emit(self, record):
        msg = self.format(record)
        if not msg.strip():
            return
        # Transform raw HTTP log into a meaningful model message
        for url_fragment, model_label in _MODEL_URL_MAP.items():
            if url_fragment in msg:
                self._queue.put(f"   {model_label} API call completed")
                return
        # Skip unrecognised httpx lines
        return


async def run_prd_pipeline(
    input_path: str = None,
    github_urls: list = None,
    documents: list = None,
    event_queue: queue_module.Queue = None
) -> str:
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
            "prd": "",
            "review": {},
            "score": 0,
            "iteration": 0,
            "best_prd": "",
            "best_score": 0
        }
        
        result = await prd_pipeline.ainvoke(initial_state)

        if result["score"] >= 80:
            prd_text = extract_text(result["prd"])
        else:
            best_prd = result.get("best_prd", "")
            if best_prd and result.get("best_score", 0) > result["score"]:
                prd_text = extract_text(best_prd)
            else:
                prd_text = extract_text(result["prd"])

        return prd_text
    finally:
        if event_queue:
            sys.stdout = original_stdout
        if log_handler:
            logging.getLogger("httpx").removeHandler(log_handler)

# =========================
# RUN
# =========================

async def main():
    start_time = time.time()
    print("🚀 Starting PRD Generation Pipeline\n")
    
    # Example with code input
    result = await prd_pipeline.ainvoke({
        "input_path": "/Users/kavinkumarbaskar/Downloads/testing-cobol/zosconnect-sample-cobol-apirequester",
        "github_urls": None,
        "documents": None,
        "code_analysis": None,
        "document_analysis": None,
        "analysis": {},
        "prd": "",
        "review": {},
        "score": 0,
        "iteration": 0,
        "best_prd": "",
        "best_score": 0
    })

    # Use best PRD if max iterations reached without hitting 80%
    if result["score"] >= 80:
        prd_text = extract_text(result["prd"])
        print(f"\n   Using current PRD (score: {result['score']}/100)")
    else:
        best_prd = result.get("best_prd", "")
        if best_prd and result.get("best_score", 0) > result["score"]:
            prd_text = extract_text(best_prd)
            print(f"\n   Using best PRD from earlier iteration (score: {result['best_score']}/100 vs final: {result['score']}/100)")
        else:
            prd_text = extract_text(result["prd"])
            print(f"\n   Using final PRD (score: {result['score']}/100)")
    print("\n" + "=" * 60)
    
    with open("final_prd.md", "w") as f:
        f.write(prd_text)
    
    elapsed = time.time() - start_time
    mins, secs = divmod(int(elapsed), 60)
    print(f"\n📄 PRD saved to final_prd.md")
    print(f"⏱️  Pipeline completed in {mins}m {secs}s")

if __name__ == "__main__":
    asyncio.run(main())