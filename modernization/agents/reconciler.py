"""Modernization Blueprint Reconciler Agent - Fixes issues identified by reviewer."""

import json
import time
from typing import Any, Dict

from config import get_settings
from modernization.prompt import MODERNIZATION_RECONCILER_PROMPT
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


def reconcile_modernization_blueprint(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Reconcile modernization blueprint by fixing critical issues identified by reviewer.
    
    Args:
        state: Modernization state dict with 'blueprint', 'review', and 'analysis' keys
        
    Returns:
        Dict with 'blueprint' and 'iteration' incremented
    """
    iteration = state.get("iteration", 0) + 1
    print(f"\n[Step 3/3] Reconciling Modernization Blueprint (iteration {iteration})...")
    
    blueprint_str = json.dumps(state["blueprint"], indent=2) if isinstance(state["blueprint"], dict) else str(state["blueprint"])
    review_str = json.dumps(state["review"], indent=2)
    
    analysis_summary = state.get("analysis", {})
    if isinstance(analysis_summary, dict):
        analysis_str = f"Project: {analysis_summary.get('project_name', 'Unknown')}, Current Tech: {analysis_summary.get('current_tech', 'Unknown')}"
    else:
        analysis_str = str(analysis_summary)[:500]
    
    prompt = MODERNIZATION_RECONCILER_PROMPT.format(
        blueprint=blueprint_str,
        review=review_str,
        analysis=analysis_str,
    )
    
    try:
        result = get_claude_client().invoke([HumanMessage(content=prompt)])
    except Exception as e:
        print(f"   Error: Claude invocation failed: {e}")
        return {
            "blueprint": state["blueprint"],
            "iteration": iteration,
        }
    
    try:
        if result.content.strip().startswith('{'):
            parsed = json.loads(result.content)
            if 'blueprint' in parsed:
                blueprint_value = parsed['blueprint']
                if isinstance(blueprint_value, dict) and 'markdown' in blueprint_value:
                    reconciled = blueprint_value['markdown']
                elif isinstance(blueprint_value, dict):
                    reconciled = json.dumps(blueprint_value)
                else:
                    reconciled = str(blueprint_value)
            else:
                reconciled = result.content
        else:
            reconciled = result.content
    except json.JSONDecodeError as e:
        print(f"   Warning: Could not parse reconciler response: {e}")
        reconciled = result.content
    
    return {
        "blueprint": reconciled,
        "iteration": iteration,
    }

