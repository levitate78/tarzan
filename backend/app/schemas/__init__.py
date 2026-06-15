"""Pydantic v2 schemas matching the OpenAPI contract."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, HttpUrl, field_validator


# ── Base ───────────────────────────────────────────────────────────────────────

class OrmBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ── Auth ───────────────────────────────────────────────────────────────────────

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


# ── Enums ──────────────────────────────────────────────────────────────────────

class UserRole(str, Enum):
    admin = "admin"
    lead = "lead"
    member = "member"
    viewer = "viewer"


class SkillCategory(str, Enum):
    languages = "languages"
    frameworks = "frameworks"
    cloud = "cloud"
    databases = "databases"
    devops = "devops"
    testing = "testing"
    soft_skills = "soft_skills"
    other = "other"


class IssueStatus(str, Enum):
    todo = "todo"
    in_progress = "in_progress"
    in_review = "in_review"
    blocked = "blocked"
    done = "done"
    cancelled = "cancelled"


class IssuePriority(str, Enum):
    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"


class MRState(str, Enum):
    opened = "opened"
    closed = "closed"
    merged = "merged"
    locked = "locked"


class ConnectorType(str, Enum):
    jira = "jira"
    gitlab = "gitlab"


# ── Skills ─────────────────────────────────────────────────────────────────────

class SkillCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    category: SkillCategory
    description: Optional[str] = None


class SkillResponse(OrmBase):
    id: str
    name: str
    category: str
    description: Optional[str] = None
    created_at: datetime


class SkillLevelSet(BaseModel):
    skill_id: str
    level: int = Field(..., ge=0, le=5)
    aspiration_level: Optional[int] = Field(None, ge=0, le=5)


class SkillLevelResponse(OrmBase):
    skill: SkillResponse
    level: int
    aspiration_level: Optional[int] = None
    updated_at: datetime


class TeamSkillsMatrix(BaseModel):
    skill: SkillResponse
    member_count: int
    average_level: float
    gap_count: int
    distribution: dict[str, int]


# ── Users ──────────────────────────────────────────────────────────────────────

class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    full_name: str
    password: str = Field(..., min_length=12)
    avatar_url: Optional[str] = None
    gitlab_username: Optional[str] = None
    jira_username: Optional[str] = None
    role: UserRole = UserRole.member


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None
    gitlab_username: Optional[str] = None
    jira_username: Optional[str] = None
    role: Optional[UserRole] = None


class UserResponse(OrmBase):
    id: str
    username: str
    email: str
    full_name: str
    avatar_url: Optional[str] = None
    gitlab_username: Optional[str] = None
    jira_username: Optional[str] = None
    role: str
    is_active: bool
    created_at: datetime
    skill_levels: list[SkillLevelResponse] = []


class UserSummary(OrmBase):
    id: str
    username: str
    full_name: str
    avatar_url: Optional[str] = None
    role: str


# ── GitLab Merge Requests (forward declarations) ──────────────────────────────

class GitLabMRSummary(OrmBase):
    id: str
    external_id: int
    project_name: str
    title: str
    state: str
    web_url: Optional[str] = None
    review_age_hours: float
    breached: bool


# ── Jira Issues ────────────────────────────────────────────────────────────────

class JiraIssueResponse(OrmBase):
    id: str
    key: str
    project_key: str
    summary: str
    description: Optional[str] = None
    status: str
    priority: Optional[str] = None
    issue_type: str
    assignee: Optional[UserSummary] = None
    reporter_username: Optional[str] = None
    labels: list[str] = []
    jira_url: Optional[str] = None
    jira_created_at: Optional[datetime] = None
    jira_updated_at: Optional[datetime] = None
    synced_at: datetime
    linked_mrs: list[GitLabMRSummary] = []


class IssueReassignRequest(BaseModel):
    assignee_username: str


# ── GitLab Merge Requests ─────────────────────────────────────────────────────

class JiraIssueSummary(OrmBase):
    id: str
    key: str
    project_key: str
    summary: str
    status: str
    priority: Optional[str] = None
    jira_url: Optional[str] = None


class GitLabMRResponse(OrmBase):
    id: str
    external_id: int
    project_id: int
    project_name: str
    title: str
    description: Optional[str] = None
    state: str
    author_username: Optional[str] = None
    assignee_usernames: list[str] = []
    reviewer_usernames: list[str] = []
    source_branch: Optional[str] = None
    target_branch: Optional[str] = None
    web_url: Optional[str] = None
    jira_issue_keys: list[str] = []
    review_age_hours: float
    breach_threshold_hours: float
    breached: bool
    mr_created_at: Optional[datetime] = None
    mr_updated_at: Optional[datetime] = None
    synced_at: datetime
    linked_issues: list[JiraIssueSummary] = []


# ── Dashboard ──────────────────────────────────────────────────────────────────

class MemberSummary(BaseModel):
    user: UserSummary
    open_issues: int
    blocked_issues: int
    open_mrs: int
    breached_mrs: int


class TeamDashboard(BaseModel):
    total_members: int
    total_open_issues: int
    total_open_mrs: int
    issues_by_status: dict[str, int]
    mrs_breached: int
    members: list[MemberSummary]


# ── Connector Config ───────────────────────────────────────────────────────────

class ConnectorConfigCreate(BaseModel):
    connector_type: ConnectorType
    base_url: str
    token: str
    project_keys: list[str] = []
    project_ids: list[int] = []
    poll_interval_seconds: int = Field(default=300, ge=60)


class ConnectorConfigResponse(OrmBase):
    id: str
    connector_type: str
    base_url: str
    project_keys: list[str] = []
    project_ids: list[int] = []
    poll_interval_seconds: int
    last_synced_at: Optional[datetime] = None
    is_healthy: bool
    created_at: datetime


# ── Pagination ─────────────────────────────────────────────────────────────────

class PaginatedResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[Any]


# ── Config ─────────────────────────────────────────────────────────────────────

class ReviewThresholdResponse(BaseModel):
    threshold_hours: float


class ReviewThresholdUpdate(BaseModel):
    threshold_hours: float = Field(..., gt=0)
