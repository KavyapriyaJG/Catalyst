from pathlib import Path
from typing import Set, Tuple

SUPPORTED_DOCUMENT_EXTENSIONS: Set[str] = {'.pdf', '.txt', '.docx'}
MAX_FILE_SIZE = 100 * 1024 * 1024


def validate_file_extension(filename: str, allowed_extensions: Set[str] = SUPPORTED_DOCUMENT_EXTENSIONS) -> bool:
    if not filename:
        return False
    file_ext = Path(filename).suffix.lower()
    return file_ext in allowed_extensions


def validate_file_size(file_size: int, max_size: int = MAX_FILE_SIZE) -> Tuple[bool, str]:
    if file_size > max_size:
        return False, f"File too large. Maximum size: {max_size / (1024*1024):.0f} MB"
    return True, ""


def get_extension_error_message(allowed_extensions: Set[str] = SUPPORTED_DOCUMENT_EXTENSIONS) -> str:
    return f"File type not allowed. Supported types: {', '.join(sorted(allowed_extensions))}"



