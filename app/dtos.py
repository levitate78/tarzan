"""Plain dataclasses returned by the service layer.

Services never return ORM model objects to blueprints/templates — these DTOs
keep the presentation layer decoupled from the database schema.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class ProfileDTO:
    username: str
    name: str
    avatar_path: str | None = None
    jira_account_id: str | None = None
    gitlab_username: str | None = None


@dataclass(frozen=True)
class SkillDTO:
    id: int
    name: str
    deprecated: bool = False


@dataclass(frozen=True)
class MatrixEntryDTO:
    skill_id: int
    skill_name: str
    skill_deprecated: bool
    current_level: str
    aspiration_level: str | None = None


@dataclass(frozen=True)
class SkillSummaryDTO:
    skill_id: int
    skill_name: str
    deprecated: bool
    level_counts: dict[str, int] = field(default_factory=dict)
    aspiration_count: int = 0


@dataclass(frozen=True)
class ImportRowError:
    """One failed row of a bulk skills import. The message describes the
    problem without echoing the invalid value (Requirement 10.3)."""

    row_number: int
    field: str
    message: str


@dataclass(frozen=True)
class SkillsImportResult:
    """Outcome of a bulk skills import. Imports are atomic: either every row
    was applied (``errors`` is empty) or nothing was (Requirement 13.3)."""

    imported_count: int = 0
    member_count: int = 0
    created_skills: tuple = ()
    errors: tuple = ()

    @property
    def ok(self) -> bool:
        return not self.errors


@dataclass(frozen=True)
class RemovalResult:
    skill_id: int
    skill_name: str
    reference_count: int
    removed: bool
    deprecated: bool


@dataclass(frozen=True)
class WorkItemDTO:
    issue_key: str
    summary: str
    assignee_account_id: str | None
    assignee_display_name: str | None
    status: str
    priority: str | None
    is_blocked: bool = False
    is_in_review: bool = False
    fetched_at: datetime | None = None


@dataclass(frozen=True)
class WorkItemDetailDTO:
    issue_key: str
    summary: str
    assignee_account_id: str | None
    assignee_display_name: str | None
    status: str
    priority: str | None
    description: str = ""
    comments: tuple = ()
    labels: tuple = ()
    linked_issues: tuple = ()
    is_blocked: bool = False
    is_in_review: bool = False


@dataclass(frozen=True)
class TicketLinkDTO:
    issue_key: str
    resolved: bool
    url: str | None = None


@dataclass(frozen=True)
class MergeRequestDTO:
    gitlab_id: int
    project_id: int
    title: str
    author_username: str | None
    target_branch: str | None
    source_branch: str | None
    review_status: str
    created_at: datetime | None
    web_url: str | None = None
    reviewers: tuple = ()
    ticket_links: tuple = ()
    overdue: bool = False


@dataclass(frozen=True)
class FetchResult:
    source_id: str
    success: bool
    item_count: int = 0
    error: str | None = None


@dataclass(frozen=True)
class ReassignResult:
    issue_key: str
    new_assignee_account_id: str
    new_assignee_display_name: str | None


@dataclass(frozen=True)
class RefreshStatusDTO:
    source_id: str
    display_name: str
    last_success: datetime | None
    consecutive_failures: int
    stale: bool

    @property
    def failing(self) -> bool:
        from app.constants import STALENESS_FAILURE_THRESHOLD

        return self.consecutive_failures >= STALENESS_FAILURE_THRESHOLD
