from fastapi import UploadFile

from backlog_generation.epic_agent import JiraEpicsOutput, generate_jira_epics


async def parse_uploaded_files(files: list[UploadFile]) -> list[dict[str, str]]:
    """Read and decode a list of uploaded files into content dicts."""
    parsed: list[dict[str, str]] = []
    for file in files:
        raw_bytes = await file.read()
        if not raw_bytes:
            continue
        try:
            content = raw_bytes.decode("utf-8")
        except UnicodeDecodeError:
            content = raw_bytes.decode("latin-1", errors="ignore")
        parsed.append({"filename": file.filename or "document.txt", "content": content})
    return parsed


async def generate_epics(
    prompt: str,
    uploaded_files: list[UploadFile] | None,
    epic_count: int,
) -> JiraEpicsOutput:
    """Parse uploaded files and generate Jira epics from the prompt."""
    cleaned_prompt = prompt.strip()
    if not cleaned_prompt:
        raise ValueError("Prompt cannot be empty.")

    parsed_documents = await parse_uploaded_files(uploaded_files or [])
    epics_data = generate_jira_epics(cleaned_prompt, parsed_documents, epic_count=epic_count)
    validated = JiraEpicsOutput(**epics_data)
    if not validated.epics:
        raise ValueError("Epic generation returned an empty epics list.")
    return validated
