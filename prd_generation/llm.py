from functools import lru_cache

from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI

from config import get_settings


@lru_cache(maxsize=1)
def get_llm_codex() -> ChatOpenAI:
    s = get_settings()
    return ChatOpenAI(
        model=s.AZURE_OPENAI_DEPLOYMENT_NAME,
        base_url=s.AZURE_OPENAI_ENDPOINT,
        api_key=s.AZURE_OPENAI_API_KEY,
        timeout=s.LLM_TIMEOUT,
        max_retries=s.LLM_MAX_RETRIES,
        temperature=0,
    )


@lru_cache(maxsize=1)
def get_llm_claude() -> ChatAnthropic:
    s = get_settings()
    return ChatAnthropic(
        model=s.AZURE_ANTHROPIC_DEPLOYMENT_NAME,
        anthropic_api_url=s.AZURE_ANTHROPIC_ENDPOINT,
        anthropic_api_key=s.AZURE_ANTHROPIC_API_KEY,
        timeout=s.LLM_TIMEOUT,
        max_retries=s.LLM_MAX_RETRIES,
    )


def clear_llm_cache():
    """Clear cached LLM instances (useful between pipeline runs)."""
    get_llm_codex.cache_clear()
    get_llm_claude.cache_clear()


def extract_text(content) -> str:
    """Extract plain text from LLM content (handles both str and list of blocks)."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and "text" in block:
                parts.append(block["text"])
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts)
    return str(content)
