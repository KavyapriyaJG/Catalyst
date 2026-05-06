import re
from collections.abc import Iterable
from typing import Any

from backlog_generation.epic_agent import JiraEpicOutput, JiraStoriesOutput, JiraStoryOutput
from backlog_generation.jira.document_builder import _build_epic_description, _build_story_description
from config import get_settings


def _normalize_label(label: str) -> str:
    normalized = re.sub(r"[^a-z0-9-]+", "-", label.strip().lower()).strip("-")
    return normalized[:255]


def _resolve_priority_id(priority_label: str | None = None) -> str:
    s = get_settings()
    default_priority_id = s.JIRA_DEFAULT_PRIORITY_ID or "3"
    normalized_priority = (priority_label or "").strip().lower()

    priority_map = {
        "highest": s.JIRA_PRIORITY_HIGHEST_ID,
        "high": s.JIRA_PRIORITY_HIGH_ID,
        "medium": s.JIRA_PRIORITY_MEDIUM_ID,
        "low": s.JIRA_PRIORITY_LOW_ID,
        "lowest": s.JIRA_PRIORITY_LOWEST_ID,
    }
    mapped_priority = priority_map.get(normalized_priority, "")
    return mapped_priority or default_priority_id


def _build_epic_labels(epic: JiraEpicOutput) -> list[str]:
    s = get_settings()
    configured_labels = [
        _normalize_label(label)
        for label in s.JIRA_DEFAULT_LABELS.split(",")
        if _normalize_label(label)
    ]
    derived_label = _normalize_label(epic.epic_name)

    labels: list[str] = []
    for label in [*configured_labels, derived_label]:
        if label and label not in labels:
            labels.append(label)
    return labels


def _build_story_labels(story: JiraStoryOutput, fallback_epic_id: str) -> list[str]:
    s = get_settings()
    configured_labels = [
        _normalize_label(label)
        for label in s.JIRA_STORY_DEFAULT_LABELS.split(",")
        if _normalize_label(label)
    ]

    story_epic_id = story.epic_id.strip() or fallback_epic_id.strip()
    derived_epic_label = _normalize_label(story_epic_id)

    labels: list[str] = []
    for label in [*configured_labels, "story", derived_epic_label]:
        if label and label not in labels:
            labels.append(label)
    return labels


def build_jira_bulk_epics_payload(
    epics: Iterable[JiraEpicOutput | dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    s = get_settings()
    project_id = s.JIRA_PROJECT_ID
    priority_id = _resolve_priority_id()
    issue_type_name = s.JIRA_EPIC_ISSUE_TYPE or "Epic"
    epic_name_field = s.JIRA_EPIC_NAME_FIELD

    issue_updates: list[dict[str, Any]] = []

    for epic in epics:
        validated_epic = epic if isinstance(epic, JiraEpicOutput) else JiraEpicOutput(**epic)
        fields: dict[str, Any] = {
            "project": {"id": project_id},
            "summary": validated_epic.epic_name.strip() or validated_epic.epic_summary.strip(),
            "issuetype": {"name": issue_type_name},
            "description": _build_epic_description(validated_epic),
            "labels": _build_epic_labels(validated_epic),
            "priority": {"id": priority_id},
        }

        # epic_name_field is optional because some Jira instances use the summary as the epic
        # name, while others have a dedicated field.
        if epic_name_field:
            fields[epic_name_field] = validated_epic.epic_name

        issue_updates.append({"fields": fields})

    return {"issueUpdates": issue_updates}


def build_jira_bulk_story_payload(
    stories_payload: JiraStoriesOutput | dict[str, Any],
    parent_key: str | None = None,
) -> dict[str, list[dict[str, Any]]]:
    s = get_settings()
    project_id = s.JIRA_PROJECT_ID
    issue_type_name = s.JIRA_STORY_ISSUE_TYPE or "Story"
    story_parent_field = s.JIRA_STORY_PARENT_FIELD

    validated_stories_payload = (
        stories_payload
        if isinstance(stories_payload, JiraStoriesOutput)
        else JiraStoriesOutput(**stories_payload)
    )

    if not validated_stories_payload.stories:
        raise ValueError("Story publish payload does not contain any stories.")

    parent_key_override = (parent_key or "").strip()
    issue_updates: list[dict[str, Any]] = []

    for story in validated_stories_payload.stories:
        summary = (
            story.title.strip()
            or story.summary.strip()
            or story.story_id.strip()
            or "Generated story"
        )
        story_epic_id = story.epic_id.strip() or validated_stories_payload.epic_id.strip()
        resolved_parent_key = parent_key_override or story_epic_id

        fields: dict[str, Any] = {
            "project": {"id": project_id},
            "summary": summary,
            "issuetype": {"name": issue_type_name},
            "description": _build_story_description(story, resolved_parent_key),
            "labels": _build_story_labels(story, resolved_parent_key),
            "priority": {"id": _resolve_priority_id(story.priority)},
        }

        if parent_key_override:
            fields["parent"] = {"key": parent_key_override}

        if story_parent_field and resolved_parent_key:
            fields[story_parent_field] = resolved_parent_key

        issue_updates.append({"fields": fields})

    return {"issueUpdates": issue_updates}
