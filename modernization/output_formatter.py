"""
Modernization Output Formatter - Ensures LLM generates structured blueprint instead of freeform text
"""

import json
import re
from typing import Any, Dict


# JSON Schema for Modernization output - 8 markdown sections
MODERNIZATION_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "1. EXECUTIVE SUMMARY": {"type": "string", "description": "Goals and expected benefits (markdown)"},
        "2. CURRENT STATE (AS-IS)": {"type": "string", "description": "Major modules, databases, integrations (markdown)"},
        "3. MODERNIZATION STRATEGY (7Rs)": {"type": "string", "description": "Rehost/Replatform/Refactor/Rearchitect approach (markdown)"},
        "4. TARGET ARCHITECTURE (TO-BE)": {"type": "string", "description": "New technology stack and architecture (markdown)"},
        "5. DATA MODERNIZATION": {"type": "string", "description": "Database migration and data transformation (markdown)"},
        "6. MIGRATION ROADMAP": {"type": "string", "description": "Phase-by-phase migration plan (markdown)"},
        "7. RISKS & MITIGATION": {"type": "string", "description": "Key risks and mitigation strategies (markdown)"},
        "8. NEXT STEPS": {"type": "string", "description": "Immediate actions and decision points (markdown)"}
    },
    "required": [
        "1. EXECUTIVE SUMMARY",
        "2. CURRENT STATE (AS-IS)",
        "3. MODERNIZATION STRATEGY (7Rs)",
        "4. TARGET ARCHITECTURE (TO-BE)",
        "5. DATA MODERNIZATION",
        "6. MIGRATION ROADMAP",
        "7. RISKS & MITIGATION",
        "8. NEXT STEPS"
    ]
}


def get_json_output_format_instructions() -> str:
    """
    Returns instructions to force JSON output with 8 markdown sections.
    """
    return f"""
CRITICAL: Output ONLY valid JSON (no markdown, no code fences, no text before/after):

{json.dumps(MODERNIZATION_JSON_SCHEMA, indent=2)}

RULES:
1. Response must be a single JSON object with exactly these 8 keys (all required)
2. All values are markdown strings (use markdown formatting for content)
3. No code fences, no explanations, no extra text
4. All JSON must be valid (proper escaping, balanced braces)
5. Keys must match exactly: use the numbered section titles
6. Include evidence tags [CONFIRMED], [INFERRED], [UNKNOWN] where appropriate
"""


def extract_json_from_response(response_text: str) -> Dict[str, Any]:
    """Extract JSON from response. All field values are markdown strings."""
    stripped = response_text.strip()
    
    # Remove markdown code fences if present
    if stripped.startswith("```"):
        lines = stripped.splitlines()[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    
    # Find JSON object
    json_match = re.search(r'\{.*\}', stripped, re.DOTALL)
    if json_match:
        stripped = json_match.group(0)
    
    try:
        parsed = json.loads(stripped)
        return parsed
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse JSON from response: {e}\nContent: {stripped[:200]}")


def validate_modernization_sections(data: Dict[str, Any]) -> bool:
    """Validate that all required modernization sections are present."""
    required_keys = set(MODERNIZATION_JSON_SCHEMA["required"])
    provided_keys = set(data.keys())
    
    if required_keys != provided_keys:
        missing = required_keys - provided_keys
        extra = provided_keys - required_keys
        raise ValueError(f"Schema mismatch. Missing: {missing}, Extra: {extra}")
    
    # Validate each section has content
    for key in required_keys:
        if not isinstance(data[key], str) or not data[key].strip():
            raise ValueError(f"Section '{key}' is empty or not a string")
    
    return True
