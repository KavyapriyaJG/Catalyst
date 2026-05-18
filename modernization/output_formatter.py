"""Output formatter for modernization document sections."""

from pydantic import BaseModel, Field
from typing import Optional


class ModernizationSection(BaseModel):
    """Structured modernization document section."""
    section_id: str = Field(description="Unique section identifier (e.g., executive_summary)")
    title: str = Field(description="Human-readable section title")
    content: str = Field(description="Section content (200-400 words, plain text with markdown support)")
    word_count: Optional[int] = Field(default=None, description="Word count of the content")
    
    class Config:
        json_schema_extra = {
            "example": {
                "section_id": "executive_summary",
                "title": "Executive Summary",
                "content": "Business drivers and key benefits...",
                "word_count": 287
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
                        "content": "...",
                        "word_count": 287
                    }
                ],
                "metadata": {"generated_at": "2026-05-18T10:00:00Z"}
            }
        }


# Predefined section templates with titles, descriptions, and guidelines
SECTION_TEMPLATES = {
    "executive_summary": {
        "title": "Executive Summary",
        "description": "High-level overview of business drivers, key benefits, timeline, and investment scope",
        "guidelines": """- Start with the strategic drivers and business case
- Highlight major benefits and expected outcomes
- Include timeline overview and key milestones
- Provide investment and resource scope
- End with compelling value proposition""",
    },
    "current_target_state": {
        "title": "Current State → Target State",
        "description": "Analysis of current technology stack versus desired future state with clear rationale",
        "guidelines": """- Describe current architecture and technology landscape
- Identify limitations and pain points of current state
- Define target architecture and desired state
- Explain the gap and why modernization is necessary
- Reference specific technical/business constraints""",
    },
    "implementation_approach": {
        "title": "Implementation Approach",
        "description": "Comprehensive strategy covering phases, milestones, dependencies, and go-live approach",
        "guidelines": """- Define implementation phases and sequencing
- List major workstreams and their dependencies
- Outline milestone criteria and delivery gates
- Explain go-live strategy and rollback plans
- Address integration points and parallel run considerations""",
    },
    "risks_mitigation": {
        "title": "Risks & Mitigation",
        "description": "Identification of major risks, mitigation strategies, contingency plans, and risk ownership",
        "guidelines": """- Identify top business, technical, and organizational risks
- Rate risk severity and probability
- For each risk, provide specific mitigation strategies
- Define contingency/fallback approaches
- Assign clear risk ownership and monitoring""",
    },
    "resource_timeline": {
        "title": "Resource & Timeline",
        "description": "Detailed resource requirements, timeline, budget, and key milestones",
        "guidelines": """- Define team structure and key roles required
- Specify skills and expertise needed
- Provide overall timeline with key milestones
- Estimate effort (FTE months/hours)
- Include budget and cost considerations""",
    },
    "success_metrics": {
        "title": "Success Metrics",
        "description": "Measurable KPIs, performance targets, and ROI goals to track modernization success",
        "guidelines": """- Define success criteria aligned to modernization goals
- Specify quantifiable KPIs (performance, cost, availability)
- Include baseline metrics and target improvements
- Address user experience and adoption metrics
- Define measurement and validation approach""",
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
        "word_count": len(content.split()),
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
            "word_count": len(content.split()),
        }
    
    return {
        "doc_id": doc_id,
        "doc_name": doc_name,
        "sections": formatted_sections,
        "metadata": {
            "total_sections": len(sections),
            "total_words": sum(len(content.split()) for content in sections.values()),
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
