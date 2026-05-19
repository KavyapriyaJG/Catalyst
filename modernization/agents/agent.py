"""LangGraph agent for AI-based modernization document generation."""

import asyncio
import queue as queue_module
import sys
from pathlib import Path
from typing import Optional
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import BaseMessage, HumanMessage
from langgraph.graph import START, StateGraph
from typing_extensions import TypedDict

from api.services.prd_service import get_prd
from config import get_settings
from utils.document_utils import extract_document_content, build_documents, retrieve_context
from modernization.output_formatter import (
    get_section_title,
    SECTION_TEMPLATES,
)


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


class _OutputCapture:
    """Capture stdout writes to a queue for SSE streaming."""

    def __init__(self, event_queue: queue_module.Queue, original):
        self._queue = event_queue
        self._original = original

    def write(self, text: str):
        self._original.write(text)
        for line in text.split("\n"):
            stripped = line.strip()
            if stripped:
                self._queue.put(stripped)

    def flush(self):
        self._original.flush()


class ModernizationState(TypedDict):
    """State for modernization document generation."""
    doc_id: str
    doc_name: str
    modernization_goals: Optional[str]
    linked_prds: list[str]
    source_assets: list[dict]
    messages: list[BaseMessage]
    sections: dict[str, str]  # Generated sections


def load_prd_context(prd_ids: list[str]) -> str:
    """Load context from linked PRDs.
    
    Fetches each PRD and extracts content sections as plain text.
    Returns concatenated PRD summaries (first 1000 chars each).
    """
    if not prd_ids:
        return ""
    
    context_parts = []
    for prd_id in prd_ids:
        try:
            prd = get_prd(prd_id)
            if not prd:
                continue
            
            content_dict = prd.content or {}
            if not content_dict:
                continue
                
            section_texts = []
            for section_key, section_value in content_dict.items():
                if isinstance(section_value, dict):
                    text = section_value.get("content") or section_value.get("text") or str(section_value)
                elif isinstance(section_value, str):
                    text = section_value
                else:
                    text = str(section_value)
                
                if text:
                    section_texts.append(text)
            
            combined_content = " ".join(section_texts)
            if combined_content:
                context_parts.append(f"PRD: {prd.prd_name}\n{combined_content[:1000]}")
        except Exception:
            continue
    
    return "\n\n".join(context_parts) if context_parts else ""


def load_supporting_docs_context(source_assets: list[dict], query: str = "") -> str:
    """Load and retrieve context from supporting documents using semantic search.
    
    Follows the same pattern as epic_agent:
    1. Convert raw documents to LangChain Document objects with chunking
    2. Perform semantic similarity search against query
    3. Return most relevant chunks
    
    Args:
        source_assets: List of {filename, path, uploaded_at, size} dicts
        query: Search query for semantic similarity (default: empty for all context)
    
    Returns:
        Formatted context string from most relevant document chunks
    """
    if not source_assets:
        return ""
    
    # Extract content from uploaded files
    supporting_documents = []
    for asset in source_assets:
        try:
            filepath = asset.get("path")
            filename = asset.get("filename")
            
            if not filepath:
                continue
            
            file_path = Path(filepath)
            text = extract_document_content(file_path)
            
            if text.strip():
                supporting_documents.append({
                    "filename": filename,
                    "content": text
                })
        except (ValueError, Exception):
            # Silently skip files that can't be extracted
            continue
    
    if not supporting_documents:
        return ""
    
    # Convert to LangChain documents with chunking
    documents = build_documents(supporting_documents)
    if not documents:
        return ""
    
    # Use semantic search if query provided, otherwise return all chunks
    if query:
        return retrieve_context(query, documents, top_k=6)
    else:
        # Return concatenated content of all chunks
        return "\n\n".join([doc.page_content for doc in documents])


def _create_section_prompt(
    section_id: str,
    doc_name: str,
    modernization_goals: str | None,
    prd_context: str,
    supporting_docs_context: str = "",
    section_description: str = "",
) -> str:
    """Create a professional, structured prompt for section generation.
    
    Each section has specific requirements tailored to modernization documentation.
    Supporting documents are semantically searched against the section description.
    
    If modernization_goals is not provided, the AI will analyze PRDs and documents
    to determine the current tech stack and appropriate modernization strategy.
    """
    template = SECTION_TEMPLATES.get(section_id, {})
    title = template.get("title", section_id.replace("_", " ").title())
    description = template.get("description", "")
    guidelines = template.get("guidelines", "")
    
    # Build modernization context - analyze documents if goals not provided
    if modernization_goals and modernization_goals.strip():
        modernization_context = f"Modernization Goals: {modernization_goals}"
    else:
        modernization_context = """Modernization Goals: Not explicitly provided. Analyze the PRD and supporting documentation to:
1. Identify the current technology stack and architecture
2. Determine pain points and modernization opportunities
3. Recommend a target technology direction based on industry best practices
4. Use this analysis to inform your recommendations in this section"""
    
    prompt_sections = []
    
    prompt_sections.append(
        f"""You are an enterprise modernization architect and technical strategist with expertise in system transformation, cloud migration, and technology upgrades.

Your task is to author a professional section for a comprehensive modernization strategy document.

**DOCUMENT CONTEXT:**
Document Title: {doc_name}
{modernization_context}

**SECTION TO GENERATE:**
Section Title: {title}
Section Purpose: {description}
""")
    
    if guidelines:
        prompt_sections.append(f"""**SECTION GUIDELINES:**
{guidelines}""")
    
    if prd_context:
        prompt_sections.append(f"""**CURRENT SYSTEM CONTEXT (from PRD):**
{prd_context}""")
    
    if supporting_docs_context:
        prompt_sections.append(f"""**SUPPORTING DOCUMENTATION:**
{supporting_docs_context}""")
    
    prompt_sections.append(
        """**QUALITY REQUIREMENTS:**
1. Content Quality
   - Write for executive stakeholders and technical leads
   - Use clear, professional business language
   - Ground all claims in the provided system context
   - Include specific, actionable recommendations where applicable
   - Be comprehensive but concise

2. Structure & Format
   - Use markdown formatting for clarity (headings, bold, italics, bullet points)
   - Organize content logically with clear sections/subsections
   - Use bullet points for lists of items
   - Use tables for comparisons or structured data when appropriate
   - Ensure readability and visual hierarchy

3. Content Depth
   - Provide sufficient detail to support decision-making
   - Reference specific aspects from the system context
   - Include rationale and justification for recommendations
   - Highlight critical considerations and dependencies
   - Avoid generic statements — be specific and contextual

4. Style Guidelines
   - Use "The system shall..." or "We recommend..." for requirements/recommendations
   - Maintain consistent terminology throughout
   - Use positive, forward-looking language
   - Be factual and evidence-based
   - Acknowledge assumptions and constraints

**OUTPUT INSTRUCTIONS:**
1. Generate ONLY the section body content (no title, no heading level)
2. Do NOT include introductory phrases like "In this section..." or "Here is..."
3. Start directly with the substantive content
4. Ensure the content is self-contained and can stand alone
5. Use markdown formatting for emphasis and structure
6. Review for clarity, completeness, and professional tone before finalizing""")
    
    return "\n\n".join(prompt_sections)


def generate_executive_summary(state: ModernizationState) -> ModernizationState:
    """Generate Executive Summary section."""
    print("Generating section 1 of 7: Executive Summary...")
    try:
        client = get_claude_client()
        
        prd_context = load_prd_context(state["linked_prds"])
        section_desc = SECTION_TEMPLATES["executive_summary"]["description"]
        supporting_docs_context = load_supporting_docs_context(state["source_assets"], query=section_desc)
        prompt = _create_section_prompt(
            "executive_summary",
            state["doc_name"],
            state["modernization_goals"],
            prd_context,
            supporting_docs_context,
            section_desc,
        )

        message = client.invoke([HumanMessage(content=prompt)])
        state["sections"]["executive_summary"] = message.content
        state["messages"].append(HumanMessage(content=prompt))
        state["messages"].append(message)
        print("Section 1 completed")
    except Exception as e:
        state["sections"]["executive_summary"] = f"[Error generating section: {str(e)}]"
    
    return state


def generate_current_state_assessment(state: ModernizationState) -> ModernizationState:
    """Generate Current State Assessment (AS-IS) section."""
    print("Generating section 2 of 7: Current State Assessment...")
    try:
        client = get_claude_client()
        
        prd_context = load_prd_context(state["linked_prds"])
        section_desc = SECTION_TEMPLATES["current_state_assessment"]["description"]
        supporting_docs_context = load_supporting_docs_context(state["source_assets"], query=section_desc)
        prompt = _create_section_prompt(
            "current_state_assessment",
            state["doc_name"],
            state["modernization_goals"],
            prd_context,
            supporting_docs_context,
            section_desc,
        )

        message = client.invoke(state["messages"] + [HumanMessage(content=prompt)])
        state["sections"]["current_state_assessment"] = message.content
        state["messages"].append(HumanMessage(content=prompt))
        state["messages"].append(message)
        print("Section 2 completed")
    except Exception as e:
        state["sections"]["current_state_assessment"] = f"[Error generating section: {str(e)}]"
    
    return state


def generate_modernization_strategy(state: ModernizationState) -> ModernizationState:
    """Generate Modernization Strategy (7Rs Assessment) section."""
    print("Generating section 3 of 7: Modernization Strategy...")
    try:
        client = get_claude_client()
        
        prd_context = load_prd_context(state["linked_prds"])
        section_desc = SECTION_TEMPLATES["modernization_strategy"]["description"]
        supporting_docs_context = load_supporting_docs_context(state["source_assets"], query=section_desc)
        prompt = _create_section_prompt(
            "modernization_strategy",
            state["doc_name"],
            state["modernization_goals"],
            prd_context,
            supporting_docs_context,
            section_desc,
        )

        message = client.invoke(state["messages"] + [HumanMessage(content=prompt)])
        state["sections"]["modernization_strategy"] = message.content
        state["messages"].append(HumanMessage(content=prompt))
        state["messages"].append(message)
        print("Section 3 completed")
    except Exception as e:
        state["sections"]["modernization_strategy"] = f"[Error generating section: {str(e)}]"
    
    return state


def generate_target_architecture(state: ModernizationState) -> ModernizationState:
    """Generate Target Architecture (TO-BE) section."""
    print("Generating section 4 of 7: Target Architecture...")
    try:
        client = get_claude_client()
        
        prd_context = load_prd_context(state["linked_prds"])
        section_desc = SECTION_TEMPLATES["target_architecture"]["description"]
        supporting_docs_context = load_supporting_docs_context(state["source_assets"], query=section_desc)
        prompt = _create_section_prompt(
            "target_architecture",
            state["doc_name"],
            state["modernization_goals"],
            prd_context,
            supporting_docs_context,
            section_desc,
        )

        message = client.invoke(state["messages"] + [HumanMessage(content=prompt)])
        state["sections"]["target_architecture"] = message.content
        state["messages"].append(HumanMessage(content=prompt))
        state["messages"].append(message)
        print("Section 4 completed")
    except Exception as e:
        state["sections"]["target_architecture"] = f"[Error generating section: {str(e)}]"
    
    return state


def generate_data_modernization(state: ModernizationState) -> ModernizationState:
    """Generate Data Modernization Strategy section."""
    print("Generating section 5 of 7: Data Modernization...")
    client = get_claude_client()
    
    prd_context = load_prd_context(state["linked_prds"])
    section_desc = SECTION_TEMPLATES["data_modernization"]["description"]
    supporting_docs_context = load_supporting_docs_context(state["source_assets"], query=section_desc)
    prompt = _create_section_prompt(
        "data_modernization",
        state["doc_name"],
        state["modernization_goals"],
        prd_context,
        supporting_docs_context,
        section_desc,
    )

    message = client.invoke(state["messages"] + [HumanMessage(content=prompt)])
    state["sections"]["data_modernization"] = message.content
    state["messages"].append(HumanMessage(content=prompt))
    state["messages"].append(message)
    print("Section 5 completed")
    return state


def generate_migration_roadmap(state: ModernizationState) -> ModernizationState:
    """Generate Migration Roadmap & Phasing section."""
    print("Generating section 6 of 7: Migration Roadmap...")
    client = get_claude_client()
    
    prd_context = load_prd_context(state["linked_prds"])
    section_desc = SECTION_TEMPLATES["migration_roadmap"]["description"]
    supporting_docs_context = load_supporting_docs_context(state["source_assets"], query=section_desc)
    prompt = _create_section_prompt(
        "migration_roadmap",
        state["doc_name"],
        state["modernization_goals"],
        prd_context,
        supporting_docs_context,
        section_desc,
    )

    message = client.invoke(state["messages"] + [HumanMessage(content=prompt)])
    state["sections"]["migration_roadmap"] = message.content
    state["messages"].append(HumanMessage(content=prompt))
    state["messages"].append(message)
    print("Section 6 completed")
    return state


def generate_risks_and_mitigation(state: ModernizationState) -> ModernizationState:
    """Generate Risks & Mitigation section."""
    print("Generating section 7 of 7: Risks & Mitigation...")
    try:
        client = get_claude_client()
        
        prd_context = load_prd_context(state["linked_prds"])
        section_desc = SECTION_TEMPLATES["risks_and_mitigation"]["description"]
        supporting_docs_context = load_supporting_docs_context(state["source_assets"], query=section_desc)
        prompt = _create_section_prompt(
            "risks_and_mitigation",
            state["doc_name"],
            state["modernization_goals"],
            prd_context,
            supporting_docs_context,
            section_desc,
        )

        message = client.invoke(state["messages"] + [HumanMessage(content=prompt)])
        state["sections"]["risks_and_mitigation"] = message.content
        state["messages"].append(HumanMessage(content=prompt))
        state["messages"].append(message)
        print("Section 7 completed")
    except Exception as e:
        state["sections"]["risks_and_mitigation"] = f"[Error generating section: {str(e)}]"
    
    return state


def build_modernization_agent():
    """Build the modernization document generation agent."""
    from langgraph.graph import END
    
    workflow = StateGraph(ModernizationState)
    
    workflow.add_node("executive_summary", generate_executive_summary)
    workflow.add_node("current_state_assessment", generate_current_state_assessment)
    workflow.add_node("modernization_strategy", generate_modernization_strategy)
    workflow.add_node("target_architecture", generate_target_architecture)
    workflow.add_node("data_modernization", generate_data_modernization)
    workflow.add_node("migration_roadmap", generate_migration_roadmap)
    workflow.add_node("risks_and_mitigation", generate_risks_and_mitigation)
    
    workflow.add_edge(START, "executive_summary")
    workflow.add_edge("executive_summary", "current_state_assessment")
    workflow.add_edge("current_state_assessment", "modernization_strategy")
    workflow.add_edge("modernization_strategy", "target_architecture")
    workflow.add_edge("target_architecture", "data_modernization")
    workflow.add_edge("data_modernization", "migration_roadmap")
    workflow.add_edge("migration_roadmap", "risks_and_mitigation")
    workflow.add_edge("risks_and_mitigation", END)
    
    return workflow.compile()


async def generate_modernization_doc(
    doc_id: str,
    doc_name: str,
    modernization_goals: Optional[str] = None,
    linked_prds: Optional[list[str]] = None,
    source_assets: Optional[list[dict]] = None,
    event_queue: Optional[queue_module.Queue] = None,
) -> dict[str, str]:
    """Generate all modernization document sections (async).
    
    Args:
        doc_id: Document ID
        doc_name: Document name
        modernization_goals: Optional modernization goals - AI will analyze documents if not provided
        linked_prds: List of linked PRD IDs
        source_assets: List of uploaded supporting documents with metadata
        event_queue: Optional queue for SSE streaming of progress events
    
    Returns:
        Dictionary of section_id -> content
    """
    def _generate_sync():
        """Blocking generation wrapped for async execution."""
        # Capture stdout if event_queue is provided
        original_stdout = sys.stdout
        if event_queue:
            sys.stdout = _OutputCapture(event_queue, original_stdout)
        
        try:
            agent = build_modernization_agent()
            
            initial_state = ModernizationState(
                doc_id=doc_id,
                doc_name=doc_name,
                modernization_goals=modernization_goals,
                linked_prds=linked_prds or [],
                source_assets=source_assets or [],
                messages=[],
                sections={},
            )
            
            result = agent.invoke(initial_state)
            return result["sections"]
        finally:
            if event_queue:
                sys.stdout = original_stdout
    
    # Run blocking operation in thread pool without blocking event loop
    return await asyncio.to_thread(_generate_sync)
