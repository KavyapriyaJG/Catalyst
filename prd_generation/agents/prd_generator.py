import time
import json
from typing import Any

from config import get_settings
from langchain_openai.chat_models.base import OpenAIContextOverflowError
from prd_generation.llm import extract_text, get_llm_codex
from prd_generation.state import AgentState
from prd_generation.output_formatter import extract_json_from_response, get_json_output_format_instructions
from prd_generation.prompts import (
    COBOL_PRD_GENERATOR_PROMPT,
    COMBINED_PRD_GENERATOR_PROMPT,
    DOCUMENT_PRD_GENERATOR_PROMPT,
)

_EMPTY_PRD = {
    "executive_summary": "PRD generation failed",
    "system_overview": "",
    "functional_requirements": "",
    "data_model": "",
    "process_flows": "",
    "business_rules": "",
    "external_interfaces": "",
    "non_functional_requirements": "",
    "risks": ""
}


def _truncate_text(value: str, max_chars: int) -> str:
    if len(value) <= max_chars:
        return value
    head = int(max_chars * 0.8)
    tail = max_chars - head
    return f"{value[:head]}\n\n[...truncated for context limit...]\n\n{value[-tail:]}"


def _analysis_to_text(analysis: Any) -> str:
    if isinstance(analysis, dict):
        return json.dumps(analysis, indent=2)
    return str(analysis)


def _soft_summarize_analysis(analysis: Any) -> Any:
    """Reduce analysis payload size while preserving key traceability context."""
    if not isinstance(analysis, dict):
        return _truncate_text(str(analysis), 50000)

    reduced = dict(analysis)

    # Keep lightweight insight slices and aggressively reduce large raw payload fields.
    for key, limit in {
        "full_code_analysis": 18000,
        "full_document_analysis": 10000,
        "analysis": 14000,
        "code_insights": 6000,
        "document_insights": 6000,
    }.items():
        value = reduced.get(key)
        if isinstance(value, str):
            reduced[key] = _truncate_text(value, limit)

    reduced["soft_summary_mode"] = True
    reduced["soft_summary_note"] = (
        "Analysis payload was reduced after a model context overflow. "
        "Use preserved insights and traceability fields first."
    )

    serialized = _analysis_to_text(reduced)
    if len(serialized) > 70000:
        reduced.pop("full_code_analysis", None)
        reduced.pop("full_document_analysis", None)
        reduced["analysis"] = _truncate_text(serialized, 50000)

    return reduced


def _sanitize_priority_meta(value: Any) -> Any:
    """Remove internal priority-mode leakage from model output before persisting PRD."""
    if isinstance(value, dict):
        return {k: _sanitize_priority_meta(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize_priority_meta(item) for item in value]
    if isinstance(value, str):
        lower = value.lower()
        blocked_tokens = [
            "given priority mode",
            "effective weights",
            "priority rationale",
            "priority mode",
            "code=100, docs=",
            "docs=100, code=",
            "auto_bias",
            "code_high",
            "docs_high",
        ]
        if any(token in lower for token in blocked_tokens):
            return ""
        return value
    return value


def generate_prd(state: AgentState):
    print(f"\n[Step 2/4] Generating PRD from analysis (JSON format)...")
    print(f"   Invoking Codex {get_settings().AZURE_OPENAI_DEPLOYMENT_NAME} for PRD generation...")
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

    analysis_payload = state.get("analysis")
    prompt = prompt_template.format(
        analysis=_analysis_to_text(analysis_payload),
        priority_mode=state.get("priority_mode", "auto_bias"),
        code_priority=state.get("code_priority", 100),
        docs_priority=state.get("docs_priority", 100),
        priority_reason=state.get("priority_reason", ""),
        json_instructions=get_json_output_format_instructions()
    )
    
    t0 = time.time()
    try:
        result = get_llm_codex().invoke(prompt)
    except OpenAIContextOverflowError:
        print("   Context window exceeded. Retrying with soft-summarized analysis...")
        reduced_analysis = _soft_summarize_analysis(analysis_payload)
        retry_prompt = prompt_template.format(
            analysis=_analysis_to_text(reduced_analysis),
            priority_mode=state.get("priority_mode", "auto_bias"),
            code_priority=state.get("code_priority", 100),
            docs_priority=state.get("docs_priority", 100),
            priority_reason=state.get("priority_reason", ""),
            json_instructions=get_json_output_format_instructions()
        )
        result = get_llm_codex().invoke(retry_prompt)
        print("   Soft-summary retry succeeded.")
    elapsed = time.time() - t0
    response_text = extract_text(result.content)
    
    try:
        prd_json = extract_json_from_response(response_text)
        prd_json = _sanitize_priority_meta(prd_json)
        print(f"   Codex responded in {int(elapsed)}s — PRD generated (JSON with {len(prd_json)} top-level fields)")
        return {"prd": prd_json}
    except ValueError as e:
        print(f"   Failed to parse PRD JSON: {e}")
        return {
            "prd": _EMPTY_PRD
        }
