import json
import os
import re
import uuid
from typing import Any, TypeVar

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_core.documents import Document
from utils.document_utils import chunk_text, build_documents, get_embeddings, retrieve_context
from langchain_groq import ChatGroq
from pydantic import BaseModel, Field
from .prompt import EPIC_SYSTEM_PROMPT, STORIES_SYSTEM_PROMPT

load_dotenv()


# EPIC_SYSTEM_PROMPT = """
# You are an expert product manager who creates Jira epics.
# Always produce implementation-ready details for engineering teams.
# Use the retrieved context from supporting documents when available.
# If information is missing, write explicit assumptions.
# Do not generate child stories.
# """.strip()


# STORIES_SYSTEM_PROMPT = """
# You are an expert agile delivery manager.
# Generate implementation-ready Jira stories from the provided epic JSON.
# Each story must clearly map to the epic and include testable acceptance criteria.
# """.strip()


class JiraEpicOutput(BaseModel):
    epic_id: str = Field(default="", description="Unique epic id")
    epic_name: str = Field(description="Epic name")
    epic_summary: str = Field(description="Short epic summary")
    business_value: str = Field(description="Business value delivered by the epic")
    scope: list[str] = Field(description="Items included in scope")
    out_of_scope: list[str] = Field(description="Items excluded from scope")
    assumptions: list[str] = Field(description="Assumptions made while drafting the epic")
    acceptance_criteria: list[str] = Field(description="Testable acceptance criteria")
    risks_and_dependencies: list[str] = Field(description="Risks and dependencies")


class JiraEpicsOutput(BaseModel):
    epics: list[JiraEpicOutput] = Field(default_factory=list)


class JiraStoryOutput(BaseModel):
    story_id: str = Field(default="", description="Unique story id")
    epic_id: str = Field(default="", description="Parent epic id")
    title: str = Field(description="Story title")
    summary: str = Field(description="Short story summary")
    description: str = Field(description="Detailed story description")
    acceptance_criteria: list[str] = Field(default_factory=list)
    priority: str = Field(default="Medium", description="Priority label")


class JiraStoriesOutput(BaseModel):
    epic_id: str = Field(default="", description="Parent epic id")
    stories: list[JiraStoryOutput] = Field(default_factory=list)


TModel = TypeVar("TModel", bound=BaseModel)


def _get_llm() -> ChatGroq:
    groq_api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not groq_api_key:
        raise ValueError("Missing GROQ_API_KEY environment variable.")

    model_name = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b").strip()
    return ChatGroq(model=model_name, api_key=groq_api_key, temperature=0.2)





def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower()).strip("-")
    return slug[:24] if slug else "epic"


def _make_epic_id(epic_name: str) -> str:
    suffix = uuid.uuid4().hex[:6].upper()
    return f"EPIC-{_slugify(epic_name).upper()}-{suffix}"


def _make_story_id(epic_id: str, index: int) -> str:
    return f"{epic_id}-STORY-{index:02d}"


def _invoke_structured_agent(
    user_message: str,
    output_model: type[TModel],
    system_prompt: str,
) -> TModel:
    llm = _get_llm()

    try:
        agent = create_agent(
            model=llm,
            tools=[],
            system_prompt=system_prompt,
            response_format=output_model,
        )
        result = agent.invoke({"messages": [{"role": "user", "content": user_message}]})
        structured = result.get("structured_response")
        if isinstance(structured, output_model):
            return structured
        if isinstance(structured, dict):
            return output_model(**structured)
    except Exception:
        pass

    structured_llm = llm.with_structured_output(output_model)
    result = structured_llm.invoke(user_message)
    if isinstance(result, output_model):
        return result
    if isinstance(result, dict):
        return output_model(**result)

    raise ValueError("Structured generation failed.")


def generate_jira_epics(
    user_prompt: str,
    supporting_documents: list[dict[str, str]] | None = None,
    epic_count: int = 3,
) -> dict[str, Any]:
    clean_prompt = user_prompt.strip()
    if not clean_prompt:
        raise ValueError("Prompt cannot be empty.")

    safe_epic_count = max(1, min(epic_count, 10))

    user_message = (
        "Generate a list of Jira epics in structured JSON format.\n\n"
        f"User prompt:\n{clean_prompt}\n\n"
        f"Generate exactly {safe_epic_count} distinct epics.\n"
        "No supporting documents were provided. Use the prompt alone and state assumptions clearly."
    )

    if supporting_documents:
        documents = build_documents(supporting_documents)
        # print(f"Built {len(documents)} document chunks from supporting documents.")
        if documents:
            retrieved_context = retrieve_context(clean_prompt, documents)
            # print(f"Retrieved context:\n{retrieved_context}\n--- End of retrieved context ---")
            if retrieved_context:
                user_message = (
                    "Generate a list of Jira epics in structured JSON format.\n\n"
                    f"User prompt:\n{clean_prompt}\n\n"
                    "Retrieved supporting context from embeddings:\n"
                    f"{retrieved_context}\n\n"
                    f"Generate exactly {safe_epic_count} distinct epics.\n"
                    "Use both prompt and retrieved context. Make each epic concise and implementation-ready."
                )

    structured_output = _invoke_structured_agent(
        user_message=user_message,
        output_model=JiraEpicsOutput,
        system_prompt=EPIC_SYSTEM_PROMPT,
    )
    payload = structured_output.model_dump()

    epics_payload = payload.get("epics", [])
    if not isinstance(epics_payload, list) or not epics_payload:
        raise ValueError("Epic generation returned an empty epics list.")

    normalized_epics: list[dict[str, Any]] = []
    for epic in epics_payload[:safe_epic_count]:
        if not isinstance(epic, dict):
            continue

        epic_id = str(epic.get("epic_id", "")).strip()
        if not epic_id:
            epic_id = _make_epic_id(str(epic.get("epic_name", "Epic")))

        normalized_epics.append({**epic, "epic_id": epic_id})

    if not normalized_epics:
        raise ValueError("Epic generation failed to produce valid epic entries.")

    payload["epics"] = normalized_epics

    return payload


def generate_jira_epic(
    user_prompt: str,
    supporting_documents: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    # Backward-compatible wrapper returning the first generated epic.
    epics_payload = generate_jira_epics(
        user_prompt=user_prompt,
        supporting_documents=supporting_documents,
        epic_count=1,
    )
    epics = epics_payload.get("epics", [])
    if not epics:
        raise ValueError("Epic generation returned an empty epics list.")
    return epics[0]


def generate_stories_from_epic(
    epic_payload: dict[str, Any],
    story_count: int = 5,
) -> dict[str, Any]:
    if not epic_payload:
        raise ValueError("Epic payload cannot be empty.")

    safe_story_count = max(1, min(story_count, 20))

    epic_id = str(epic_payload.get("epic_id", "")).strip()
    if not epic_id:
        epic_id = _make_epic_id(str(epic_payload.get("epic_name", "Epic")))
        epic_payload = {**epic_payload, "epic_id": epic_id}

    user_message = (
        "Generate Jira stories from the given epic JSON.\n\n"
        f"Epic JSON:\n{json.dumps(epic_payload, indent=2)}\n\n"
        f"Generate exactly {safe_story_count} stories."
    )

    structured_output = _invoke_structured_agent(
        user_message=user_message,
        output_model=JiraStoriesOutput,
        system_prompt=STORIES_SYSTEM_PROMPT,
    )
    payload = structured_output.model_dump()

    payload_epic_id = str(payload.get("epic_id", "")).strip() or epic_id
    payload["epic_id"] = payload_epic_id

    normalized_stories: list[dict[str, Any]] = []
    for index, story in enumerate(payload.get("stories", []), start=1):
        story_epic_id = str(story.get("epic_id", "")).strip() or payload_epic_id
        story_id = str(story.get("story_id", "")).strip() or _make_story_id(
            payload_epic_id, index
        )

        normalized_story = {
            **story,
            "epic_id": story_epic_id,
            "story_id": story_id,
        }
        normalized_stories.append(normalized_story)

    payload["stories"] = normalized_stories[:safe_story_count]

    return payload
