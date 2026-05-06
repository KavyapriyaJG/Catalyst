import json
import re
import time

from config import get_settings
from prd_generation.llm import extract_text, get_llm_claude
from prd_generation.state import AgentState
from prd_generation.prompts import REVIEWER_PROMPT


def review_prd(state: AgentState):
    print(f"\n[Step 3/4] Reviewing PRD (iteration {state.get('iteration', 0) + 1})...")
    print(f"   Invoking Claude {get_settings().AZURE_ANTHROPIC_DEPLOYMENT_NAME} for PRD review...")
    prd_json_str = json.dumps(state['prd'], indent=2) if isinstance(state['prd'], dict) else str(state['prd'])
    prompt = REVIEWER_PROMPT.format(
        analysis=json.dumps(state['analysis'], indent=2) if isinstance(state['analysis'], dict) else str(state['analysis']),
        prd=prd_json_str
    )
    t0 = time.time()
    result = get_llm_claude().invoke(prompt)
    elapsed = time.time() - t0
    print(f"   Claude responded in {int(elapsed)}s")
    raw = extract_text(result.content)

    # Strip markdown code fences if present
    stripped = raw.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        lines = lines[1:]
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

    update = {"review": parsed, "score": score}
    prev_best = state.get("best_score", 0)
    if score > prev_best:
        print(f"   New best score: {score} (previous best: {prev_best})")
        update["best_prd"] = state["prd"]
        update["best_score"] = score
    return update
