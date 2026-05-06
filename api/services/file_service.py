import re
from datetime import datetime

from api.models import UploadedFileItem
from config import get_settings


def _sanitize_filename(filename: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9._-]", "_", filename)
    safe = safe.strip("._/\\")
    return safe[:255] or "file"


def save_upload(contents: bytes, file_id: str, name: str) -> str:
    """Write uploaded file bytes to the uploads directory.

    Returns:
        Formatted upload timestamp string.
    """
    filepath = get_settings().UPLOADS_DIR / f"{file_id}###{name}"
    filepath.write_bytes(contents)
    return datetime.now().strftime("%m/%d/%Y, %I:%M:%S %p")


def list_uploads() -> list[UploadedFileItem]:
    """Return all uploaded files sorted by modification time descending."""
    uploads_dir = get_settings().UPLOADS_DIR
    if not uploads_dir.exists():
        return []

    items: list[UploadedFileItem] = []
    for filepath in sorted(uploads_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if not filepath.is_file():
            continue
        parts = filepath.name.split("###", 1)
        if len(parts) != 2:
            continue
        file_id, original_name = parts
        file_size = filepath.stat().st_size
        uploaded_at = datetime.fromtimestamp(filepath.stat().st_mtime).strftime(
            "%m/%d/%Y, %I:%M:%S %p"
        )
        items.append(
            UploadedFileItem(
                id=file_id,
                name=original_name,
                size=f"{file_size / 1024:.1f} KB" if file_size > 0 else "0 KB",
                uploaded_at=uploaded_at,
                file=None,
            )
        )
    return items


def delete_upload(file_id: str) -> bool:
    """Delete an uploaded file by its ID.

    Returns:
        True if deleted, False if no matching file was found.
    """
    uploads_dir = get_settings().UPLOADS_DIR
    if not uploads_dir.exists():
        return False

    for filepath in uploads_dir.iterdir():
        if filepath.name.startswith(f"{file_id}###"):
            filepath.unlink()
            return True
    return False
