from typing import Any

from backlog_generation.epic_agent import JiraEpicOutput, JiraStoryOutput


def _jira_text_node(text: str) -> dict[str, str]:
    return {"type": "text", "text": text}


def _jira_paragraph(text: str) -> dict[str, Any]:
    return {
        "type": "paragraph",
        "content": [_jira_text_node(text.strip())],
    }


def _jira_heading(text: str, level: int = 3) -> dict[str, Any]:
    return {
        "type": "heading",
        "attrs": {"level": level},
        "content": [_jira_text_node(text)],
    }


def _jira_bullet_list(items: list[str]) -> dict[str, Any]:
    return {
        "type": "bulletList",
        "content": [
            {
                "type": "listItem",
                "content": [_jira_paragraph(item)],
            }
            for item in items
        ],
    }


def _clean_items(items: list[str]) -> list[str]:
    return [item.strip() for item in items if item and item.strip()]


def _append_list_section(
    content: list[dict[str, Any]], heading: str, items: list[str]
) -> None:
    cleaned_items = _clean_items(items)
    if not cleaned_items:
        return
    content.append(_jira_heading(heading))
    content.append(_jira_bullet_list(cleaned_items))


def _build_epic_description(epic: JiraEpicOutput) -> dict[str, Any]:
    content: list[dict[str, Any]] = []

    if epic.epic_summary.strip():
        content.append(_jira_paragraph(epic.epic_summary))

    if epic.epic_id.strip():
        content.append(_jira_heading("Epic ID"))
        content.append(_jira_paragraph(epic.epic_id))

    if epic.business_value.strip():
        content.append(_jira_heading("Business Value"))
        content.append(_jira_paragraph(epic.business_value))

    _append_list_section(content, "Scope", epic.scope)
    _append_list_section(content, "Out of Scope", epic.out_of_scope)
    _append_list_section(content, "Assumptions", epic.assumptions)
    _append_list_section(content, "Acceptance Criteria", epic.acceptance_criteria)
    _append_list_section(content, "Risks and Dependencies", epic.risks_and_dependencies)

    if not content:
        content.append(_jira_paragraph(epic.epic_name.strip() or "Generated epic"))

    return {"type": "doc", "version": 1, "content": content}


def _build_story_description(story: JiraStoryOutput, fallback_epic_id: str) -> dict[str, Any]:
    content: list[dict[str, Any]] = []

    detailed_description = story.description.strip()
    summary = story.summary.strip()

    if detailed_description:
        content.append(_jira_paragraph(detailed_description))
    elif summary:
        content.append(_jira_paragraph(summary))

    if story.story_id.strip():
        content.append(_jira_heading("Story ID"))
        content.append(_jira_paragraph(story.story_id))

    story_epic_id = story.epic_id.strip() or fallback_epic_id.strip()
    if story_epic_id:
        content.append(_jira_heading("Epic ID"))
        content.append(_jira_paragraph(story_epic_id))

    _append_list_section(content, "Acceptance Criteria", story.acceptance_criteria)

    if not content:
        content.append(_jira_paragraph(story.title.strip() or "Generated story"))

    return {"type": "doc", "version": 1, "content": content}
