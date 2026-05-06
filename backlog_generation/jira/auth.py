import base64

from config import get_settings


def jira_auth_header() -> str:
    """Return the Basic auth header value for Jira API requests."""
    s = get_settings()
    auth_value = base64.b64encode(
        f"{s.JIRA_USERNAME}:{s.JIRA_AUTH_TOKEN}".encode("utf-8")
    ).decode("utf-8")
    return f"Basic {auth_value}"


def jira_bulk_endpoint() -> str:
    """Return the Jira bulk issue create endpoint URL."""
    return get_settings().JIRA_BULK_ISSUES_ENDPOINT


def validate_jira_credentials() -> tuple[str, str, str]:
    """Validate that all required Jira credentials are set and return them.

    Returns:
        Tuple of (JIRA_BASE_URL, JIRA_USERNAME, JIRA_AUTH_TOKEN).

    Raises:
        ValueError: If any credential is missing.
    """
    s = get_settings()
    if not s.JIRA_BASE_URL or not s.JIRA_USERNAME or not s.JIRA_AUTH_TOKEN:
        raise ValueError(
            "Missing Jira credentials. Set JIRA_BASE_URL, JIRA_USERNAME, JIRA_AUTH_TOKEN."
        )
    return s.JIRA_BASE_URL, s.JIRA_USERNAME, s.JIRA_AUTH_TOKEN
