"""Shared approval system for all artifact types across the application."""

from approval.models import ApprovalEvent
from approval.submissions import get_activity_submissions

__all__ = ["ApprovalEvent", "get_activity_submissions"]
