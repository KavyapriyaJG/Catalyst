import shutil
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile

from backlog_generation.epic_agent import JiraEpicsOutput, generate_jira_epics
from config import get_settings


async def parse_uploaded_files(
    files: list[UploadFile],
) -> tuple[list[dict[str, str]], list[tuple[str, bytes]]]:
    """Read and decode a list of uploaded files.

    Returns:
        A 2-tuple of (content_dicts, raw_bytes_pairs) where raw_bytes_pairs is
        a list of (filename, bytes) suitable for persisting to disk.
    """
    parsed: list[dict[str, str]] = []
    raw_pairs: list[tuple[str, bytes]] = []
    for file in files:
        raw_bytes = await file.read()
        if not raw_bytes:
            continue
        filename = file.filename or "document.txt"
        try:
            content = raw_bytes.decode("utf-8")
        except UnicodeDecodeError:
            content = raw_bytes.decode("latin-1", errors="ignore")
        parsed.append({"filename": filename, "content": content})
        raw_pairs.append((filename, raw_bytes))
    return parsed, raw_pairs


async def generate_epics(
    prompt: str,
    uploaded_files: list[UploadFile] | None,
    epic_count: int,
) -> tuple[JiraEpicsOutput, str]:
    """Parse uploaded files, generate Jira epics, persist files + DB records.

    Returns:
        A 2-tuple of (validated_epics, backlog_id).
    """
    cleaned_prompt = prompt.strip()
    if not cleaned_prompt:
        raise ValueError("Prompt cannot be empty.")

    parsed_documents, raw_pairs = await parse_uploaded_files(uploaded_files or [])

    # Pre-allocate backlog_id for the filesystem directory.
    backlog_id = uuid4().hex
    settings = get_settings()
    backlog_dir: Path = settings.BACKLOG_FILES_DIR / backlog_id

    # Copy uploaded files to Backlog_Files/{backlog_id}/ before LLM call so
    # the directory exists even if generation fails.
    if raw_pairs:
        backlog_dir.mkdir(parents=True, exist_ok=True)
        for filename, raw_bytes in raw_pairs:
            safe_name = Path(filename).name  # strip any directory component
            dest = backlog_dir / safe_name
            dest.write_bytes(raw_bytes)

    try:
        epics_data = generate_jira_epics(cleaned_prompt, parsed_documents, epic_count=epic_count)
        validated = JiraEpicsOutput(**epics_data)
        if not validated.epics:
            raise ValueError("Epic generation returned an empty epics list.")
    except Exception:
        # Clean up files if LLM fails
        if backlog_dir.exists():
            shutil.rmtree(backlog_dir, ignore_errors=True)
        raise

    # Persist backlog + epics to the database.
    from api.services import backlog_service  # late import to avoid circular dependency

    source_filenames = [name for name, _ in raw_pairs]
    db_result = backlog_service.create_and_save_epics(
        prompt=cleaned_prompt,
        epics=validated.epics,
        source_files=source_filenames,
        backlog_id=backlog_id,
    )
    real_backlog_id: str = db_result["id"]

    # If the real DB-assigned UUID differs from our pre-allocated one, rename dir.
    if raw_pairs and real_backlog_id != backlog_id:
        real_dir = settings.BACKLOG_FILES_DIR / real_backlog_id
        backlog_dir.rename(real_dir)

    return validated, real_backlog_id
