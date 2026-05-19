"""Output formatter for modernization document sections."""

from pydantic import BaseModel, Field
from typing import Optional


class ModernizationSection(BaseModel):
    """Structured modernization document section."""
    section_id: str = Field(description="Unique section identifier (e.g., executive_summary)")
    title: str = Field(description="Human-readable section title")
    content: str = Field(description="Section content (plain text with markdown support)")
    
    class Config:
        json_schema_extra = {
            "example": {
                "section_id": "executive_summary",
                "title": "Executive Summary",
                "content": "Business drivers and key benefits..."
            }
        }


class ModernizationDocumentOutput(BaseModel):
    """Complete modernization document output with all sections."""
    doc_id: str = Field(description="Document ID")
    doc_name: str = Field(description="Document name")
    sections: list[ModernizationSection] = Field(description="All modernization sections")
    metadata: dict = Field(default_factory=dict, description="Additional metadata")
    
    class Config:
        json_schema_extra = {
            "example": {
                "doc_id": "mod-123",
                "doc_name": "Platform Modernization Initiative",
                "sections": [
                    {
                        "section_id": "executive_summary",
                        "title": "Executive Summary",
                        "content": "..."
                    }
                ],
                "metadata": {"generated_at": "2026-05-18T10:00:00Z"}
            }
        }


# Predefined section templates with titles, descriptions, and guidelines
# Focused on technical migration strategy with explicit AWS 7Rs framework
SECTION_TEMPLATES = {
    "executive_summary": {
        "title": "Executive Summary",
        "description": "Business drivers for modernization, strategic goals, expected outcomes, and value proposition",
        "guidelines": """- Define why modernization is critical (technical debt, business constraints, compliance)
- State strategic modernization goals and success criteria
- Summarize expected business outcomes and benefits
- Highlight key technical or operational improvements
- Outline scope and transformation approach at high level""",
    },
    "current_state_assessment": {
        "title": "Current State Assessment (AS-IS)",
        "description": "Inventory of legacy systems, modules, components, dependencies, pain points, and technical debt",
        "guidelines": """- Document core legacy systems/modules and their functions
- Describe current technology stack, databases, and integrations
- Identify system interdependencies and data flows
- List pain points, scalability issues, and technical debt
- Assess maintainability, performance bottlenecks, and complexity hotspots
- Document any compliance or security gaps""",
    },
    "modernization_strategy": {
        "title": "Modernization Strategy (7Rs Assessment)",
        "description": "Detailed 7Rs evaluation for each system/module with rationale and approach selection",
        "guidelines": """- For each major system/module, evaluate all 7Rs:
  * **Rehost**: Lift & shift to cloud as-is
  * **Replatform**: Lift, tinker & shift (minimal refactoring)
  * **Refactor/Re-architect**: Modernize code/architecture for cloud
  * **Repurchase**: Replace with SaaS/COTS solution
  * **Retire**: Decommission unnecessary systems
  * **Retain**: Keep on-premises or as-is
  * **Re-invest**: Enhance for strategic advantage
- Justify the selected 7R for each component
- Document trade-offs and constraints
- Identify dependencies and integration concerns""",
    },
    "target_architecture": {
        "title": "Target Architecture (TO-BE)",
        "description": "Future state technology architecture, cloud design, microservices, APIs, and deployment model",
        "guidelines": """- Design target cloud/modern architecture
- Define service boundaries and microservices approach
- Specify technology stack choices (languages, frameworks, databases)
- Document API design and integration patterns
- Describe deployment model (containers, serverless, hybrid)
- Address scalability, resilience, and high-availability design
- Map business capabilities to technical services""",
    },
    "data_modernization": {
        "title": "Data Modernization Strategy",
        "description": "Data migration approach, schema mapping, transformation rules, and data validation",
        "guidelines": """- Inventory legacy data structures, copybooks, and databases
- Define data mapping from legacy to target systems
- Document transformation and cleansing rules
- Address data quality and reconciliation approach
- Specify data migration method (batch, CDC, real-time sync)
- Define cut-over strategy and data validation checkpoints
- Document rollback procedures for data issues""",
    },
    "migration_roadmap": {
        "title": "Migration Roadmap & Phasing",
        "description": "Phase-wise migration plan, execution sequencing, coexistence strategy, and cutover approach",
        "guidelines": """- Define migration phases and wave sequencing
- Identify quick wins and pilot candidates
- Document dependencies between phases
- Plan parallel run and coexistence periods
- Specify system cutover sequence and timing
- Address fallback and rollback procedures
- Define success criteria for each phase completion""",
    },
    "risks_and_mitigation": {
        "title": "Risks & Mitigation",
        "description": "Technical, operational, and business risks with mitigation strategies and contingency plans",
        "guidelines": """- Identify major technical risks (compatibility, performance, data integrity)
- Document operational risks (downtime, support gaps, skills)
- List business risks (cost overruns, schedule delays, adoption)
- For each risk, define:
  * Risk probability and impact
  * Mitigation strategy and preventive actions
  * Contingency plan if risk materializes
  * Owner and monitoring approach
- Prioritize risks by severity
- Define escalation procedures for critical issues""",
    },
}


def get_section_title(section_id: str) -> str:
    """Get human-readable title for a section ID."""
    return SECTION_TEMPLATES.get(section_id, {}).get("title", section_id.replace("_", " ").title())


def format_section_for_display(section_id: str, content: str) -> dict:
    """Format section content for UI display."""
    return {
        "section_id": section_id,
        "title": get_section_title(section_id),
        "content": content,
    }


def format_document_for_storage(
    doc_id: str,
    doc_name: str,
    sections: dict[str, str],
) -> dict:
    """
    Format document sections for database storage.
    
    Args:
        doc_id: Document identifier
        doc_name: Document name
        sections: Dictionary of section_id -> content
    
    Returns:
        Dictionary formatted for JSONB storage
    """
    formatted_sections = {}
    for section_id, content in sections.items():
        formatted_sections[section_id] = {
            "title": get_section_title(section_id),
            "content": content,
        }
    
    return {
        "doc_id": doc_id,
        "doc_name": doc_name,
        "sections": formatted_sections,
        "metadata": {
            "total_sections": len(sections),
        }
    }


def format_sections_as_record(sections: dict[str, str]) -> dict[str, str]:
    """
    Convert sections to the Record<string, string> format used by UI.
    
    Args:
        sections: Dictionary of section_id -> content
    
    Returns:
        Dictionary of title -> content for UI rendering
    """
    return {
        get_section_title(section_id): content
        for section_id, content in sections.items()
    }
