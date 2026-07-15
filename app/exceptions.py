"""Typed application exceptions.

Raised by the service layer and caught at the blueprint boundary; raw
exceptions from external libraries never reach the templates.
"""

from __future__ import annotations


class TarzanError(Exception):
    """Base class for all application errors."""


class ValidationError(TarzanError):
    """User-supplied input failed validation. Never echoes the invalid value."""

    def __init__(self, message: str, field: str | None = None):
        super().__init__(message)
        self.field = field


class ConflictError(TarzanError):
    """The submitted data conflicts with existing records (e.g. duplicates)."""


class NotFoundError(TarzanError):
    """The requested record does not exist."""


class StorageError(TarzanError):
    """The database or credential store is unavailable."""


class ReassignError(TarzanError):
    """The Jira API rejected a work item reassignment."""


class ReassignTimeoutError(ReassignError):
    """The Jira API did not respond to a reassignment within the timeout."""


class JiraClientError(TarzanError):
    """A Jira API call failed (network, timeout, or HTTP error)."""

    def __init__(self, message: str, source: str = "jira"):
        super().__init__(message)
        self.source = source


class GitLabClientError(TarzanError):
    """A GitLab API call failed (network, timeout, or HTTP error)."""

    def __init__(self, message: str, source: str = "gitlab"):
        super().__init__(message)
        self.source = source
