import time

from config import get_settings
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

    prompt = prompt_template.format(
        analysis=state['analysis'],
        json_instructions=get_json_output_format_instructions()
    )
    
    t0 = time.time()
    result = get_llm_codex().invoke(prompt)
    elapsed = time.time() - t0
    response_text = extract_text(result.content)
    
    try:
        prd_json = extract_json_from_response(response_text)
        print(f"   Codex responded in {int(elapsed)}s — PRD generated (JSON with {len(prd_json)} top-level fields)")
        return {"prd": prd_json}
    except ValueError as e:
        print(f"   Failed to parse PRD JSON: {e}")
        return {
            "prd": _EMPTY_PRD
        }
