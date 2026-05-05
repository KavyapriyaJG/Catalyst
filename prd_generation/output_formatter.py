"""
PRD Output Formatter - Ensures LLM generates structured JSON instead of text
"""

import json
import re
from typing import Any, Dict


# JSON Schema for PRD output
PRD_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "executive_summary": {
            "type": "string",
            "description": "2-3 sentence high-level overview of the system"
        },
        "system_overview": {
            "type": "object",
            "properties": {
                "purpose": {"type": "string"},
                "scope": {"type": "string"},
                "domain": {"type": "string"},
                "key_stakeholders": {"type": "array", "items": {"type": "string"}}
            }
        },
        "functional_requirements": {
            "type": "object",
            "additionalProperties": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "description": "FR-XXX"},
                        "statement": {"type": "string", "description": "The system shall..."},
                        "input": {"type": "string", "description": "What triggers or feeds this requirement"},
                        "processing": {"type": "string", "description": "What the system does"},
                        "output": {"type": "string", "description": "What is produced"},
                        "acceptance_criteria": {"type": "array", "items": {"type": "string"}},
                        "evidence_tag": {
                            "type": "string",
                            "enum": ["CONFIRMED", "INFERRED", "UNKNOWN", "CODE-ONLY", "DOC-ONLY", "CONFLICTING"]
                        },
                        "source": {"type": "string", "description": "Reference to code/doc source"}
                    }
                }
            }
        },
        "data_model": {
            "type": "object",
            "properties": {
                "entities": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "description": {"type": "string"},
                            "attributes": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "name": {"type": "string"},
                                        "type": {"type": "string"},
                                        "required": {"type": "boolean"},
                                        "description": {"type": "string"}
                                    }
                                }
                            },
                            "keys": {
                                "type": "object",
                                "properties": {
                                    "primary": {"type": "string"},
                                    "foreign": {"type": "array", "items": {"type": "string"}}
                                }
                            }
                        }
                    }
                },
                "relationships": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "from_entity": {"type": "string"},
                            "to_entity": {"type": "string"},
                            "type": {"type": "string", "enum": ["one-to-one", "one-to-many", "many-to-many"]},
                            "description": {"type": "string"}
                        }
                    }
                }
            }
        },
        "process_flows": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Workflow name"},
                    "description": {"type": "string"},
                    "entry_point": {"type": "string", "description": "How workflow starts"},
                    "steps": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "step_number": {"type": "integer"},
                                "action": {"type": "string"},
                                "decision": {"type": "string", "description": "If this is a decision point"},
                                "data_consumed": {"type": "array", "items": {"type": "string"}},
                                "data_produced": {"type": "array", "items": {"type": "string"}}
                            }
                        }
                    },
                    "exit_point": {"type": "string", "description": "How workflow ends"},
                    "error_handling": {"type": "string"},
                    "evidence_tag": {
                        "type": "string",
                        "enum": ["CONFIRMED", "INFERRED", "UNKNOWN", "CODE-ONLY", "DOC-ONLY", "CONFLICTING"]
                    }
                }
            }
        },
        "business_rules": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "BR-XXX"},
                    "statement": {"type": "string"},
                    "rule_type": {
                        "type": "string",
                        "enum": ["validation", "calculation", "decision", "policy", "constraint", "state_transition"]
                    },
                    "condition": {"type": "string", "description": "When rule applies"},
                    "action": {"type": "string", "description": "What happens when condition is true"},
                    "verification_method": {"type": "string", "description": "How to test this rule"},
                    "source": {"type": "string", "description": "Code program/document section"},
                    "evidence_tag": {
                        "type": "string",
                        "enum": ["CONFIRMED", "INFERRED", "UNKNOWN", "CODE-ONLY", "DOC-ONLY", "CONFLICTING"]
                    }
                }
            }
        },
        "external_interfaces": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "type": {"type": "string", "enum": ["file", "api", "database", "service", "call", "stream"]},
                    "direction": {"type": "string", "enum": ["inbound", "outbound", "bidirectional"]},
                    "protocol": {"type": "string"},
                    "data_format": {"type": "string"},
                    "description": {"type": "string"},
                    "volume": {"type": "string", "description": "Frequency or volume metrics"},
                    "evidence_tag": {
                        "type": "string",
                        "enum": ["CONFIRMED", "INFERRED", "UNKNOWN", "CODE-ONLY", "DOC-ONLY"]
                    }
                }
            }
        },
        "non_functional_requirements": {
            "type": "object",
            "properties": {
                "performance": {
                    "type": "array",
                    "items": {"type": "object", "properties": {"metric": {"type": "string"}, "target": {"type": "string"}}}
                },
                "scalability": {
                    "type": "array",
                    "items": {"type": "object", "properties": {"metric": {"type": "string"}, "target": {"type": "string"}}}
                },
                "reliability": {
                    "type": "array",
                    "items": {"type": "object", "properties": {"metric": {"type": "string"}, "target": {"type": "string"}}}
                },
                "security": {
                    "type": "array",
                    "items": {"type": "object", "properties": {"requirement": {"type": "string"}}}
                },
                "compliance": {
                    "type": "array",
                    "items": {"type": "object", "properties": {"standard": {"type": "string"}, "requirement": {"type": "string"}}}
                }
            }
        },
        "risks_and_mitigations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "RISK-XXX"},
                    "description": {"type": "string"},
                    "severity": {"type": "string", "enum": ["HIGH", "MEDIUM", "LOW"]},
                    "probability": {"type": "string", "enum": ["high", "medium", "low"]},
                    "impact": {"type": "string"},
                    "mitigation_strategy": {"type": "string"},
                    "source": {"type": "string", "description": "Where risk was identified"}
                }
            }
        }
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
        "risks_and_mitigations"
    ]
}


def get_json_output_format_instructions() -> str:
    """
    Returns instructions that should be prepended to prompts to force JSON output.
    """
    return f"""
CRITICAL OUTPUT REQUIREMENT — Generate ONLY Valid JSON:

1. Your ENTIRE response must be a single valid JSON object matching this schema:
{json.dumps(PRD_JSON_SCHEMA, indent=2)}

2. STRICT RULES:
   - Do NOT use markdown, do NOT use code fences (```), do NOT add any text before or after JSON
   - Do NOT include comments or explanations
   - Ensure all JSON is valid (proper escaping, balanced braces, valid types)
   - All string values must properly escape special characters
   - Use arrays for lists, objects for maps
   - Every required field must be present

3. Evidence Tags:
   - Every major claim must include ONE of: [CONFIRMED], [INFERRED], [UNKNOWN], [CODE-ONLY], [DOC-ONLY], [CONFLICTING]
   - Use [CONFIRMED] only for statements directly observed in source material
   - Use [INFERRED] for reasonable deductions
   - Use [UNKNOWN] when information cannot be determined
   - For combined code+doc analysis: use [CODE-ONLY], [DOC-ONLY], [CONFLICTING]

4. Field Requirements:
   - Functional Requirements: Group by feature area (keys: "User Management", "Data Processing", etc.)
   - Business Rules: Include condition → action mappings for testability
   - Acceptance Criteria: Make each criterion independently verifiable
   - Data Types: Use standard types (string, integer, decimal, boolean, date, array, object)
   - Process Flows: Include entry point, numbered steps with decisions, exit point

5. Completeness:
   - All 9 required sections must be present and substantive
   - Functional requirements must be grouped and number sequentially (FR-001, FR-002, etc.)
   - Business rules must be sequentially numbered (BR-001, BR-002, etc.)
   - Risks must be rated HIGH/MEDIUM/LOW with justification

6. Start your response with: {{
   End your response with: }}
   Nothing before the opening brace or after the closing brace.
"""


def extract_json_from_response(response_text: str) -> Dict[str, Any]:
    """Extract and parse JSON from LLM response, handling markdown code fences."""
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
        raise ValueError(f"Failed to parse JSON response: {e}\nFirst 500 chars: {stripped[:500]}")
