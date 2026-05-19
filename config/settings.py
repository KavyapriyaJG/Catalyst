from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Jira core ───────────────────────────────────────────────
    JIRA_BASE_URL: str = ""
    JIRA_USERNAME: str = ""
    JIRA_AUTH_TOKEN: str = ""
    JIRA_PROJECT_ID: str = ""
    JIRA_BULK_ISSUES_ENDPOINT: str = ""

    # ── Jira ingestion ──────────────────────────────────────────
    JIRA_BATCH_SIZE: int = 50
    JIRA_BATCHES_TO_BE_PROCESSED_COUNT: int = 10
    JIRA_FETCH_ISSUES_JQL: str = (
        "project=TEST AND created>=-365d ORDER BY created DESC"
    )
    JIRA_FETCH_TIMEOUT: int = 60
    JIRA_ISSUE_FETCH_TIMEOUT: int = 20

    # ── Jira issue types / fields ───────────────────────────────
    JIRA_EPIC_ISSUE_TYPE: str = "Epic"
    JIRA_EPIC_NAME_FIELD: str = ""
    JIRA_STORY_ISSUE_TYPE: str = "Story"
    JIRA_STORY_PARENT_FIELD: str = ""

    # ── Jira labels ─────────────────────────────────────────────
    JIRA_DEFAULT_LABELS: str = ""
    JIRA_STORY_DEFAULT_LABELS: str = ""

    # ── Jira priority IDs ───────────────────────────────────────
    JIRA_DEFAULT_PRIORITY_ID: str = "3"
    JIRA_PRIORITY_HIGHEST_ID: str = ""
    JIRA_PRIORITY_HIGH_ID: str = ""
    JIRA_PRIORITY_MEDIUM_ID: str = ""
    JIRA_PRIORITY_LOW_ID: str = ""
    JIRA_PRIORITY_LOWEST_ID: str = ""

    # ── Groq LLM ────────────────────────────────────────────────
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "openai/gpt-oss-120b"

    # ── Azure OpenAI (Codex) ─────────────────────────────────────
    AZURE_OPENAI_DEPLOYMENT_NAME: str = "gpt-5.3-codex"
    AZURE_OPENAI_ENDPOINT: str | None = None
    AZURE_OPENAI_API_KEY: str | None = None

    # ── Azure Anthropic (Claude) ─────────────────────────────────
    AZURE_ANTHROPIC_DEPLOYMENT_NAME: str = "claude-opus-4-7"
    AZURE_ANTHROPIC_ENDPOINT: str | None = None
    AZURE_ANTHROPIC_API_KEY: str | None = None

    # ── LLM call behaviour ───────────────────────────────────────
    LLM_TIMEOUT: int = 900
    LLM_MAX_RETRIES: int = 2

    # ── Embeddings ───────────────────────────────────────────────
    HUGGINGFACE_EMBEDDING_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"

    # ── Text chunking ────────────────────────────────────────────
    CHUNK_SIZE: int = 1200
    CHUNK_OVERLAP: int = 200
    SEMANTIC_TOP_K: int = 6

    # ── Epic / story generation limits ───────────────────────────
    MAX_EPICS: int = 10
    MAX_STORIES: int = 20

    # ── PRD review loop ──────────────────────────────────────────
    PRD_MAX_ITERATIONS: int = 4
    PRD_SCORE_THRESHOLD: float = 80.0

    # ── Modernization review loop ────────────────────────────────
    MODERNIZATION_MAX_ITERATIONS: int = 1
    MODERNIZATION_SCORE_THRESHOLD: float = 65.0

    # ── File upload ──────────────────────────────────────────────
    MAX_UPLOAD_SIZE_MB: int = 50

    # ── CORS ─────────────────────────────────────────────────────
    ALLOWED_ORIGINS: list[str] = [
        "http://localhost:8080",
        "http://127.0.0.1:8080",
        "http://localhost:8081",
        "http://127.0.0.1:8081",
    ]

    # ── UI / client ──────────────────────────────────────────────
    API_URL: str = "http://localhost:8000/agent"

    # ── Code scanning ────────────────────────────────────────────
    COBOL_EXTENSIONS: set[str] = {".cob", ".cbl", ".cpy"}
    SCAN_OTHER_NAMES: set[str] = {"Makefile", "Dockerfile"}
    SCAN_EXCLUDED_DIRS: set[str] = {".git", ".github", "node_modules"}

    # ── Resolved filesystem paths (not env-configurable) ─────────
    WORKSPACE_DIR: Path = _PROJECT_ROOT / "workspace"
    GENERATED_PRDS_DIR: Path = _PROJECT_ROOT / "generated_prds"
    UPLOADS_DIR: Path = _PROJECT_ROOT / "uploads"
    BACKLOG_FILES_DIR: Path = _PROJECT_ROOT / "Backlog_Files"
    MODELS_EMBEDDINGS_DIR: Path = _PROJECT_ROOT / "models" / "embeddings"

    # ── Derived helpers (computed, not from env) ─────────────────
    @model_validator(mode="after")
    def _fill_derived_fields(self) -> "Settings":
        if not self.JIRA_STORY_DEFAULT_LABELS:
            self.JIRA_STORY_DEFAULT_LABELS = self.JIRA_DEFAULT_LABELS
        if not self.JIRA_BULK_ISSUES_ENDPOINT and self.JIRA_BASE_URL:
            self.JIRA_BULK_ISSUES_ENDPOINT = (
                self.JIRA_BASE_URL.rstrip("/") + "/rest/api/3/issue/bulk"
            )
        return self

    @property
    def max_upload_size_bytes(self) -> int:
        return self.MAX_UPLOAD_SIZE_MB * 1024 * 1024


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
