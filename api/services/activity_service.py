"""Service layer for activity/approval submissions across all artifact types."""

from approval.submissions import get_activity_submissions


def get_all_submissions() -> list[dict]:
    """Fetch all persisted submissions from approval_events table."""
    return get_activity_submissions()
