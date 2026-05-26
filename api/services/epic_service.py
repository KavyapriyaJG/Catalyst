import shutil
import json
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile
from sqlalchemy import select

from backlog_generation.epic_agent import JiraEpicsOutput, generate_jira_epics
from backlog_generation.db import get_session
from config import get_settings
from api.services import backlog_service
from modernization.models import ModernizationDocRecord


def _modernization_record_to_text(record: ModernizationDocRecord) -> str:
    lines: list[str] = [f"# Modernization Document: {record.name}"]

    if record.modernization_goals:
        lines.append("## Modernization Goals")
        lines.append(record.modernization_goals)

    if isinstance(record.generated_sections, dict) and record.generated_sections:
        for section, value in record.generated_sections.items():
            lines.append(f"## {section}")
            if isinstance(value, str):
                lines.append(value)
            else:
                lines.append(json.dumps(value, indent=2))
    elif record.description:
        lines.append("## Summary")
        lines.append(record.description)

    return "\n\n".join(lines).strip()


def _load_modernization_documents_for_prds(prd_ids: list[str] | None) -> list[dict[str, str]]:
    if not prd_ids:
        return []

    with get_session() as session:
        records = session.scalars(
            select(ModernizationDocRecord).order_by(ModernizationDocRecord.updated_at.desc())
        ).all()

    target_ids = set(prd_ids)
    matched_docs: list[dict[str, str]] = []
    seen_doc_ids: set[str] = set()

    for record in records:
        linked_prds = set(record.linked_prds or [])
        if not linked_prds.intersection(target_ids):
            continue
        if record.id in seen_doc_ids:
            continue
        seen_doc_ids.add(record.id)

        content = _modernization_record_to_text(record)
        if not content:
            continue
        matched_docs.append({
            "filename": f"modernization_{record.id}.md",
            "content": content,
        })

    return matched_docs


def _load_modernization_documents_by_ids(doc_ids: list[str] | None) -> list[dict[str, str]]:
    if not doc_ids:
        return []

    with get_session() as session:
        records = session.scalars(
            select(ModernizationDocRecord).where(ModernizationDocRecord.id.in_(doc_ids))
        ).all()

    by_id = {record.id: record for record in records}
    docs: list[dict[str, str]] = []
    seen: set[str] = set()
    for doc_id in doc_ids:
        if doc_id in seen:
            continue
        seen.add(doc_id)
        record = by_id.get(doc_id)
        if not record:
            continue
        content = _modernization_record_to_text(record)
        if not content:
            continue
        docs.append(
            {
                "filename": f"modernization_{record.id}.md",
                "content": content,
            }
        )
    return docs


def _load_architecture_explanations_for_prds(prd_ids: list[str] | None) -> list[dict[str, str]]:
    if not prd_ids:
        return []

    root = get_settings().GENERATED_DESIGNS_DIR
    if not root.exists():
        return []

    latest_by_prd: dict[str, tuple[str, str, str]] = {}
    for child in root.iterdir():
        if not child.is_dir():
            continue
        manifest_path = child / "manifest.json"
        if not manifest_path.exists():
            continue

        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(manifest, dict):
            continue
        if manifest.get("diagram_type") != "architecture":
            continue

        prd_id = str(manifest.get("prd_id", "")).strip()
        if not prd_id or prd_id not in prd_ids:
            continue

        explanation_file = child / str(manifest.get("explanation_file", "explanation.md"))
        if not explanation_file.exists():
            continue

        artifact_name = str(manifest.get("artifact_name", "Architecture"))
        updated_at = str(manifest.get("updated_at", ""))

        # Keep only the latest architecture explanation per PRD.
        if prd_id in latest_by_prd and latest_by_prd[prd_id][0] >= updated_at:
            continue

        try:
            explanation = explanation_file.read_text(encoding="utf-8").strip()
        except Exception:
            continue
        if not explanation:
            continue

        latest_by_prd[prd_id] = (updated_at, artifact_name, explanation)

    docs: list[dict[str, str]] = []
    for prd_id, (_, artifact_name, explanation) in latest_by_prd.items():
        docs.append({
            "filename": f"architecture_explanation_{prd_id}.md",
            "content": f"# Architecture Diagram Explanation: {artifact_name}\n\n{explanation}",
        })
    return docs


def _load_design_artifact_explanations_by_ids(artifact_ids: list[str] | None) -> list[dict[str, str]]:
    if not artifact_ids:
        return []

    root = get_settings().GENERATED_DESIGNS_DIR
    if not root.exists():
        return []

    docs: list[dict[str, str]] = []
    seen: set[str] = set()
    for artifact_id in artifact_ids:
        artifact_id = str(artifact_id).strip()
        if not artifact_id or artifact_id in seen:
            continue
        seen.add(artifact_id)

        artifact_dir = root / artifact_id
        manifest_path = artifact_dir / "manifest.json"
        if not manifest_path.exists():
            continue

        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(manifest, dict):
            continue

        explanation_file = artifact_dir / str(manifest.get("explanation_file", "explanation.md"))
        if not explanation_file.exists():
            continue

        try:
            explanation = explanation_file.read_text(encoding="utf-8").strip()
        except Exception:
            continue
        if not explanation:
            continue

        artifact_name = str(manifest.get("artifact_name", "Design Artifact"))
        diagram_type = str(manifest.get("diagram_type", "unknown"))
        docs.append(
            {
                "filename": f"design_explanation_{artifact_id}.md",
                "content": f"# Design Diagram Explanation: {artifact_name} ({diagram_type})\n\n{explanation}",
            }
        )

    return docs


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
    prd_documents: list[dict[str, str]] | None = None,
    selected_prd_ids: list[str] | None = None,
    selected_modernization_doc_ids: list[str] | None = None,
    selected_design_artifact_ids: list[str] | None = None,
) -> tuple[JiraEpicsOutput, str]:
    """Parse uploaded files, generate Jira epics, persist files + DB records.

    Args:
        prompt: The epic generation prompt.
        uploaded_files: Optional uploaded files to parse.
        epic_count: Number of epics to generate.
        prd_documents: Optional PRD documents fetched from database.
        selected_prd_ids: Optional selected PRD ids to enrich context with
            linked modernization docs and architecture explanations.
        selected_modernization_doc_ids: Optional selected modernization document
            IDs to include explicitly.
        selected_design_artifact_ids: Optional selected design artifact IDs
            (database/api/architecture/etc.) whose explanation should be included.

    Returns:
        A 2-tuple of (validated_epics, backlog_id).
    """
    cleaned_prompt = prompt.strip()
    if not cleaned_prompt:
        raise ValueError("Prompt cannot be empty.")

    all_documents, raw_pairs = await parse_uploaded_files(uploaded_files or [])
    if prd_documents:
        all_documents.extend(prd_documents)

    if selected_modernization_doc_ids:
        all_documents.extend(_load_modernization_documents_by_ids(selected_modernization_doc_ids))
    else:
        all_documents.extend(_load_modernization_documents_for_prds(selected_prd_ids))

    if selected_design_artifact_ids:
        all_documents.extend(_load_design_artifact_explanations_by_ids(selected_design_artifact_ids))
    else:
        all_documents.extend(_load_architecture_explanations_for_prds(selected_prd_ids))

    backlog_id = uuid4().hex
    settings = get_settings()
    backlog_dir: Path = settings.BACKLOG_FILES_DIR / backlog_id

    if raw_pairs:
        backlog_dir.mkdir(parents=True, exist_ok=True)
        for filename, raw_bytes in raw_pairs:
            safe_name = Path(filename).name
            dest = backlog_dir / safe_name
            dest.write_bytes(raw_bytes)

    try:
        epics_data = generate_jira_epics(cleaned_prompt, all_documents, epic_count=epic_count)
        validated = JiraEpicsOutput(**epics_data)
        if not validated.epics:
            raise ValueError("Epic generation returned an empty epics list.")
    except Exception:
        if backlog_dir.exists():
            shutil.rmtree(backlog_dir, ignore_errors=True)
        raise

    source_filenames = [name for name, _ in raw_pairs]
    db_result = backlog_service.create_and_save_epics(
        prompt=cleaned_prompt,
        epics=validated.epics,
        source_files=source_filenames,
        backlog_id=backlog_id,
    )
    real_backlog_id: str = db_result["id"]

    if raw_pairs and real_backlog_id != backlog_id:
        real_dir = settings.BACKLOG_FILES_DIR / real_backlog_id
        backlog_dir.rename(real_dir)

    return validated, real_backlog_id
