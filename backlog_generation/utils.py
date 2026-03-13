import os
from typing import Any

from dotenv import load_dotenv

load_dotenv()


def get_from_env(name: str, default: Any = None) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        if default is not None:
            return str(default)
        raise ValueError(f"Missing required environment variable: {name}")
    return value
