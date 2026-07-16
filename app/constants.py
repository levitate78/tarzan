"""Shared constants: proficiency levels, status sets, limits."""

from __future__ import annotations

# Ordered proficiency levels (Requirement 2.3); ordering used for aspiration
# comparisons (Requirement 3.3).
LEVELS: tuple[str, ...] = ("Beginner", "Intermediate", "Advanced", "Expert")
LEVEL_ORDER: dict[str, int] = {name: index for index, name in enumerate(LEVELS)}

# Work items in these statuses are not "active" (Requirement 4.6).
DONE_STATUSES: frozenset[str] = frozenset({"done", "closed", "cancelled"})

# Avatar upload constraints (Requirement 1.7).
ALLOWED_AVATAR_MIME_TYPES: dict[str, str] = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/gif": "gif",
    "image/webp": "webp",
}
MAX_AVATAR_BYTES: int = 5 * 1024 * 1024  # 5 MiB

# Bulk skills import constraints (Requirement 13).
MAX_SKILLS_IMPORT_BYTES: int = 1024 * 1024  # 1 MiB
SKILLS_IMPORT_REQUIRED_COLUMNS: tuple[str, ...] = ("username", "skill", "current_level")
SKILLS_IMPORT_OPTIONAL_COLUMNS: tuple[str, ...] = ("aspiration_level",)

# Merge request review statuses (Requirement 6.3).
REVIEW_STATUSES: tuple[str, ...] = ("Awaiting Review", "Changes Requested", "Approved")

# Configuration keys stored in the CONFIG table.
CONFIG_REFRESH_INTERVAL = "refresh_interval_minutes"
CONFIG_REVIEW_THRESHOLD = "review_threshold_days"
CONFIG_JIRA_URL = "jira_url"
CONFIG_GITLAB_URL = "gitlab_url"
CONFIG_IN_REVIEW_STATUSES = "in_review_statuses"

DEFAULT_REFRESH_INTERVAL_MINUTES = 15  # Requirement 8.1
DEFAULT_REVIEW_THRESHOLD_DAYS = 2  # Requirement 6.6
DEFAULT_IN_REVIEW_STATUSES = "In Review"

REFRESH_INTERVAL_RANGE = (1, 60)  # minutes, Requirement 8.1
REVIEW_THRESHOLD_RANGE = (1, 30)  # days, Requirement 6.6

# Credential store keys for external API tokens.
CREDENTIAL_JIRA_TOKEN = "jira_token"
CREDENTIAL_GITLAB_TOKEN = "gitlab_token"

# Consecutive refresh failures before a staleness warning (Requirement 8.5).
STALENESS_FAILURE_THRESHOLD = 3
