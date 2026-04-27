import asyncio
from typing import TypedDict, List, Dict, Any
from langchain_openai import ChatOpenAI
from langgraph.graph import StateGraph, END
from deepagents import create_deep_agent
from langchain.tools import tool
from langchain_anthropic import ChatAnthropic
try:
    from prd_generation.prompts import ANALYSIS_AGENT_PROMPT, PRD_GENERATOR_PROMPT, REVIEWER_PROMPT, RECONCILER_PROMPT
except ImportError:
    from prompts import ANALYSIS_AGENT_PROMPT, PRD_GENERATOR_PROMPT, REVIEWER_PROMPT, RECONCILER_PROMPT
import os
import re
import sys
import json
import time
import queue as queue_module
import logging
from dotenv import load_dotenv

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
    input_path: str
    files: List[str]
    analysis: Dict[str, Any]
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
    # thinking={"type": "adaptive", "display": "summarized"},
    # thinking={"type": "adaptive"},
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
    system_prompt=ANALYSIS_AGENT_PROMPT,
    # debug=True
)

# =========================
# FIXED PRD GENERATOR
# =========================

def generate_prd(state: AgentState):
    print("\n📝 [Step 2/4] Generating PRD from analysis...")
    print(f"   Invoking Codex {os.getenv('AZURE_OPENAI_DEPLOYMENT_NAME', 'gpt-5.3-codex')} for PRD generation...")
    prompt = PRD_GENERATOR_PROMPT.format(analysis=state['analysis'])
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

def analyze(s):
    print("\n🔎 [Step 1/4] Analyzing COBOL source files...")
    input_path = s['input_path']

    # Step 1: Pre-read all files and group by module
    _build_module_registry(input_path)

    # Step 2: Let the deep agent analyze using task tool for subagent delegation
    modules_list = "\n".join(f"  - {m} ({info['files']} files, {info['chars']} chars)" for m, info in sorted(_module_summary.items()))
    print(f"   Invoking analysis agent {os.getenv('AZURE_OPENAI_DEPLOYMENT_NAME', 'gpt-5.3-codex')} with {len(_module_summary)} modules...")
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

    # Extract subagent task results from message history (much richer than LLM's summary)
    if isinstance(result, dict):
        messages = result.get("messages", [])
        print(f"   Analysis complete. {len(messages)} messages exchanged.")

        # Collect task tool_call_ids and their descriptions from AIMessages
        task_descriptions = {}  # tool_call_id -> description
        for msg in messages:
            if getattr(msg, 'type', None) == 'ai' and hasattr(msg, 'tool_calls'):
                for tc in (msg.tool_calls or []):
                    if tc.get("name") == "task":
                        task_descriptions[tc["id"]] = tc.get("args", {}).get("description", "")

        # Extract subagent results from ToolMessages
        subagent_results = []
        for msg in messages:
            if getattr(msg, 'type', None) == 'tool' and getattr(msg, 'name', None) == 'task':
                content = extract_text(getattr(msg, 'content', ''))
                if content and len(content) > 50:  # skip empty/error results
                    subagent_results.append(content)

        # Also get the LLM's final merged summary
        llm_summary = ""
        if messages:
            last_msg = messages[-1]
            content = getattr(last_msg, 'content', str(last_msg))
            llm_summary = extract_text(content)

        subagent_total = sum(len(r) for r in subagent_results)
        print(f"   Subagent results: {len(subagent_results)} modules, {subagent_total} chars total")
        print(f"   LLM summary: {len(llm_summary)} chars")

        if subagent_results:
            # Combine: LLM summary (structural overview) + all raw subagent results (detail)
            combined = (
                "=== ANALYSIS SUMMARY ===\n"
                f"{llm_summary}\n\n"
                "=== DETAILED MODULE ANALYSES ===\n\n"
                + "\n\n---\n\n".join(subagent_results)
            )
            print(f"   Combined analysis output: {len(combined)} chars")
            return {"analysis": combined}
        else:
            print(f"   WARNING: No subagent results found, using LLM summary only ({len(llm_summary)} chars)")
            return {"analysis": llm_summary}

    return {"analysis": str(result)}

graph.add_node("analyze", analyze)

graph.add_node("prd", generate_prd)
graph.add_node("review", review_prd)
graph.add_node("reconcile", reconcile)

graph.set_entry_point("analyze")
graph.add_edge("analyze", "prd")
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


async def run_prd_pipeline(input_path: str, event_queue: queue_module.Queue) -> str:
    """Run the PRD pipeline, pushing progress messages to event_queue."""
    original_stdout = sys.stdout
    sys.stdout = _OutputCapture(event_queue, original_stdout)

    log_handler = _QueueLogHandler(event_queue)
    log_handler.setFormatter(logging.Formatter("%(message)s"))
    logging.getLogger("httpx").addHandler(log_handler)

    try:
        result = await prd_pipeline.ainvoke({
            "input_path": input_path,
            "iteration": 0,
            "score": 0,
            "best_prd": "",
            "best_score": 0
        })

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
        sys.stdout = original_stdout
        logging.getLogger("httpx").removeHandler(log_handler)

# =========================
# RUN
# =========================

async def main():
    start_time = time.time()
    print("🚀 Starting COBOL Migration Analysis Pipeline\n")
    result = await prd_pipeline.ainvoke({
        # "input_path": "/Users/kavinkumarbaskar/Downloads/testing-cobol/CobolCraft",
        "input_path": "/Users/kavinkumarbaskar/Downloads/testing-cobol/zosconnect-sample-cobol-apirequester",
        "iteration": 0,
        "score": 0,
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
    # print(prd_text)
    with open("final_prd.md", "w") as f:
        f.write(prd_text)
    
    elapsed = time.time() - start_time
    mins, secs = divmod(int(elapsed), 60)
    print(f"\n📄 PRD saved to final_prd.md")
    print(f"⏱️  Pipeline completed in {mins}m {secs}s")

if __name__ == "__main__":
    asyncio.run(main())