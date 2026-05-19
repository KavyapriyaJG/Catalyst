"""Modernization Blueprint Reviewer Agent - Scores and identifies issues."""

import json
import re
import time
from typing import Any, Dict

from config import get_settings
from modernization.prompt import MODERNIZATION_REVIEWER_PROMPT
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage


def get_claude_client() -> ChatAnthropic:
    """Initialize ChatAnthropic with Azure Anthropic credentials."""
    s = get_settings()
    return ChatAnthropic(
        model=s.AZURE_ANTHROPIC_DEPLOYMENT_NAME,
        anthropic_api_url=s.AZURE_ANTHROPIC_ENDPOINT,
        anthropic_api_key=s.AZURE_ANTHROPIC_API_KEY,
        timeout=s.LLM_TIMEOUT,
        max_retries=s.LLM_MAX_RETRIES,
    )


def review_modernization_blueprint(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Review modernization blueprint and score it (0-100).
    
    Args:
        state: Modernization state dict with 'blueprint' and 'analysis' keys
        
    Returns:
        Dict with 'review', 'score', 'iteration', and optionally 'best_score'/'best_blueprint'
    """
    iteration = state.get("iteration", 0) + 1
    print(f"\n[Step 2/3] Reviewing Modernization Blueprint (iteration {iteration})...")
    
    client = get_claude_client()
    
    blueprint_str = json.dumps(state["blueprint"], indent=2) if isinstance(state["blueprint"], dict) else str(state["blueprint"])
    analysis_str = json.dumps(state["analysis"], indent=2) if isinstance(state["analysis"], dict) else str(state["analysis"])
    
    prompt = MODERNIZATION_REVIEWER_PROMPT.format(
        analysis=analysis_str,
        blueprint=blueprint_str,
    )
    
    result = client.invoke([HumanMessage(content=prompt)])
    
    raw = result.content
    stripped = raw.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    
    json_match = re.search(r'\{.*\}', stripped, re.DOTALL)
    if json_match:
        stripped = json_match.group(0)
    
    try:
        parsed = json.loads(stripped)
    except Exception:
        parsed = {
            "score": 0,
            "grade": "F",
            "issues": {"critical": ["Invalid JSON from reviewer"], "moderate": [], "minor": []}
        }
    
    score = parsed.get("score", 0)
    grade = parsed.get("grade", "F")
    
    print(f"Review score: {score}/100")
    
    update = {
        "review": parsed,
        "score": score,
    }
    
    prev_best = state.get("best_score", 0)
    if score > prev_best:
        update["best_blueprint"] = state["blueprint"]
        update["best_score"] = score
    
    return update
