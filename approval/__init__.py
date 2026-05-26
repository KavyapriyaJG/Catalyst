"""Shared approval system for all artifact types across the application."""

from approval.models import ApprovalEvent


def get_activity_submissions():
	from approval.submissions import get_activity_submissions as _get_activity_submissions

	return _get_activity_submissions()

__all__ = ["ApprovalEvent", "get_activity_submissions"]
