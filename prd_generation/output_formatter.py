"""
PRD Output Formatter - Ensures LLM generates structured JSON instead of text
"""

import json
import re
from typing import Any, Dict


# JSON Schema for PRD output - 9 markdown sections
PRD_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "executive_summary": {"type": "string", "description": "High-level overview (markdown)"},
        "system_overview": {"type": "string", "description": "Purpose, scope, domain (markdown)"},
        "functional_requirements": {"type": "string", "description": "Features and capabilities (markdown)"},
        "data_model": {"type": "string", "description": "Entities, attributes, relationships (markdown)"},
        "process_flows": {"type": "string", "description": "Workflows and interactions (markdown)"},
        "business_rules": {"type": "string", "description": "Constraints and business logic (markdown)"},
        "external_interfaces": {"type": "string", "description": "APIs, integrations, data exchanges (markdown)"},
        "non_functional_requirements": {"type": "string", "description": "Performance, scalability, security (markdown)"},
        "risks": {"type": "string", "description": "Risks and mitigations (markdown)"}
    },
    "required": [
        "executive_summary",
        "system_overview",
        "functional_requirements",
        "data_model",
        "process_flows",
        "business_rules",
        "external_interfaces",
        "non_functional_requirements",
        "risks"
    ]
}


def get_json_output_format_instructions() -> str:
    """
    Returns instructions to force JSON output with 9 markdown sections.
    """
    return f"""
CRITICAL: Output ONLY valid JSON (no markdown, no code fences, no text before/after):

{json.dumps(PRD_JSON_SCHEMA, indent=2)}

RULES:
1. Response must be a single JSON object with exactly these 9 keys (all required)
2. All values are markdown strings (use markdown formatting for content)
3. No code fences, no explanations, no extra text
4. All JSON must be valid (proper escaping, balanced braces)
5. Include evidence tags [CONFIRMED], [INFERRED], [UNKNOWN], [CODE-ONLY], [DOC-ONLY], [CONFLICTING] where appropriate
"""


def extract_json_from_response(response_text: str) -> Dict[str, Any]:
    """Extract JSON from response. All field values are markdown strings."""
    stripped = response_text.strip()
    
    if stripped.startswith("```"):
        lines = stripped.splitlines()[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    
    json_match = re.search(r'\{.*\}', stripped, re.DOTALL)
    if json_match:
        stripped = json_match.group(0)
    
    try:
        parsed = json.loads(stripped)
        return parsed
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse JSON: {e}")
