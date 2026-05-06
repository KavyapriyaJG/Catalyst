import json
import time

from config import get_settings
from prd_generation.llm import extract_text, get_llm_codex
from prd_generation.state import AgentState
from prd_generation.output_formatter import extract_json_from_response, get_json_output_format_instructions
from prd_generation.prompts import RECONCILER_PROMPT


def reconcile(state: AgentState):
    print(f"\n[Step 4/4] Reconciling PRD (iteration {state['iteration'] + 1})...")
    print(f"   Invoking Codex {get_settings().AZURE_OPENAI_DEPLOYMENT_NAME} for PRD reconciliation...")
    prd_json_str = json.dumps(state['prd'], indent=2) if isinstance(state['prd'], dict) else str(state['prd'])
    analysis_str = json.dumps(state['analysis'], indent=2) if isinstance(state['analysis'], dict) else str(state['analysis'])
    json_instructions = get_json_output_format_instructions()
    prompt = RECONCILER_PROMPT.format(
        prd=prd_json_str,
        review=json.dumps(state['review'], indent=2),
        analysis=analysis_str,
        json_instructions=json_instructions
    )
    t0 = time.time()
    result = get_llm_codex().invoke(prompt)
    elapsed = time.time() - t0
    response_text = extract_text(result.content)

    try:
        prd_json = extract_json_from_response(response_text)
        print(f"   Codex responded in {int(elapsed)}s — Reconciled PRD (JSON with {len(prd_json)} top-level fields)")
    except ValueError as e:
        print(f"   Failed to parse reconciled PRD JSON: {e}")
        prd_json = state['prd']

    return {"prd": prd_json, "iteration": state["iteration"] + 1}
