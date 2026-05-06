import shutil
import uuid
from datetime import datetime
import json

from api.models import PrdItem, PrdListItem
from config import get_settings
from utils.document_utils import extract_documents_from_uploads


def clone_repository(url: str) -> str:
    """Clone a GitHub repository into the workspace directory.

    Args:
        url: A validated GitHub URL.

    Returns:
        Absolute path string of the cloned directory.

    Raises:
        ValueError: If the git clone fails.
    """
    import git

    s = get_settings()
    workspace_dir = s.WORKSPACE_DIR
    workspace_dir.mkdir(parents=True, exist_ok=True)

    repo_name = url.rstrip("/").split("/")[-1].replace(".git", "")
    clone_dir = workspace_dir / repo_name

    if clone_dir.exists():
        shutil.rmtree(clone_dir)

    try:
        git.Repo.clone_from(url, str(clone_dir))
    except git.GitCommandError as e:
        raise ValueError(f"Failed to clone repository: {e.stderr}") from e

    return str(clone_dir)


def extract_and_validate_documents(doc_refs: list[dict]) -> list[dict[str, str]]:
    """Extract documents from the uploads directory and validate they have sufficient content.

    Args:
        doc_refs: List of document reference dicts (id, name, etc.) from the request.

    Returns:
        List of {filename, content} dicts.

    Raises:
        ValueError: If extraction fails or content is insufficient.
    """
    uploads_dir = get_settings().UPLOADS_DIR
    documents = extract_documents_from_uploads(uploads_dir, doc_refs)
    total_length = sum(len(doc.get("content", "")) for doc in documents)
    if not documents or total_length < 100:
        raise ValueError(
            f"Document extraction failed or insufficient content. "
            f"Extracted: {total_length} chars from {len(documents)} documents."
        )
    return documents


def save_prd(prd_json: dict) -> tuple[str, dict]:
    """Persist a PRD to disk and parse its structure.

    Args:
        prd_json: Parsed JSON of the generated PRD.

    Returns:
        Tuple of (filename, prd_json) where filename is the saved file's name
        and prd_json is the parsed heading-structured dict.
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    unique_id = uuid.uuid4().hex[:8]
    filename = f"prd_{timestamp}_{unique_id}.json"
    filepath = get_settings().GENERATED_PRDS_DIR / filename
    filepath.write_text(json.dumps(prd_json, indent=2))
    return filename, prd_json


def list_prds() -> list[PrdListItem]:
    """Return all saved PRDs sorted by modification time descending."""
    return [
        PrdListItem(filename=p.name)
        for p in sorted(
            get_settings().GENERATED_PRDS_DIR.glob("*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    ]


def get_prd(filename: str) -> PrdItem:
    """Load a PRD by filename and parse its content and generation timestamp.

    Raises:
        FileNotFoundError: If the file does not exist or is not a .json file.
    """
    filepath = get_settings().GENERATED_PRDS_DIR / filename
    if not filepath.exists() or filepath.suffix != ".json":
        raise FileNotFoundError(f"PRD not found: {filename}")
    prd_json = json.loads(filepath.read_text())
    try:
        parts = filename.replace(".json", "").split("_")
        if len(parts) >= 3 and parts[0] == "prd":
            date_str = parts[1]
            time_str = parts[2]
            dt_str = f"{date_str} {time_str}"
            dt = datetime.strptime(dt_str, "%Y%m%d %H%M%S")
            generated_time = dt.timestamp()
        else:
            generated_time = datetime.now().timestamp()
    except Exception:
        generated_time = datetime.now().timestamp()
    formatted_prd = {key.replace('_', ' ').title(): value for key, value in prd_json.items()}
    
    return PrdItem(filename=filepath.name, content=formatted_prd, generated_time=generated_time)

