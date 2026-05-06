import time

from deepagents import create_deep_agent

from prd_generation.llm import extract_text, get_llm_codex
from prd_generation.module_registry import ModuleRegistry
from prd_generation.state import AgentState
from prd_generation.prompts import ANALYSIS_AGENT_PROMPT


def analyze(s: AgentState):
    """Analyze COBOL source files with a per-run module registry and parallel subagents."""
    print("\n[Step 1/4] Analyzing COBOL source files...")

    registry = ModuleRegistry()
    registry.build(s["input_path"])

    list_modules_tool, get_module_source_tool = registry.make_tools()
    analysis_agent = create_deep_agent(
        model=get_llm_codex(),
        tools=[list_modules_tool, get_module_source_tool],
        system_prompt=ANALYSIS_AGENT_PROMPT,
    )

    modules_list = "\n".join(
        f"  - {m} ({info['files']} files, {info['chars']} chars)"
        for m, info in sorted(registry._summary.items())
    )
    print(f"   Invoking analysis agent (Codex) with {len(registry._summary)} modules...")
    t0 = time.time()
    result = analysis_agent.invoke({
        "messages": [{"role": "user", "content": (
            f"Analyze the COBOL codebase at {s['input_path']}.\n\n"
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

    if isinstance(result, dict):
        messages = result.get("messages", [])
        print(f"   Analysis complete. {len(messages)} messages exchanged.")

        subagent_results = []
        for msg in messages:
            if getattr(msg, "type", None) == "tool" and getattr(msg, "name", None) == "task":
                content = extract_text(getattr(msg, "content", ""))
                if content and len(content) > 50:
                    subagent_results.append(content)

        llm_summary = ""
        if messages:
            last_msg = messages[-1]
            content = getattr(last_msg, "content", str(last_msg))
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
