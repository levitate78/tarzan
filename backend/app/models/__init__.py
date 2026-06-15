"""
SQLAlchemy ORM models for Tarzan.

Sensitive columns are stored encrypted via the TypeDecorator wrappers below.
All primary keys use UUID v4 to avoid enumeration attacks.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    ARRAY,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    TypeDecorator,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.encryption import decrypt_optional, encrypt_optional
from app.database import Base


# ── Encrypted column type ──────────────────────────────────────────────────────

class EncryptedString(TypeDecorator):
    """Transparently encrypts/decrypts values using AES-256-GCM."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):  # noqa: ANN001
        return encrypt_optional(value)

    def process_result_value(self, value, dialect):  # noqa: ANN001
        return decrypt_optional(value)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


# ── Users ──────────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, default=_uuid
    )
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    email: Mapped[str] = mapped_column(EncryptedString, nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    avatar_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    gitlab_username: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    jira_username: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="member")
    hashed_password: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    skill_levels: Mapped[list["SkillLevel"]] = relationship(
        "SkillLevel", back_populates="user", cascade="all, delete-orphan"
    )
    assigned_issues: Mapped[list["JiraIssue"]] = relationship(
        "JiraIssue", back_populates="assignee"
    )


# ── Skills ─────────────────────────────────────────────────────────────────────

class Skill(Base):
    __tablename__ = "skills"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    levels: Mapped[list["SkillLevel"]] = relationship(
        "SkillLevel", back_populates="skill", cascade="all, delete-orphan"
    )


class SkillLevel(Base):
    __tablename__ = "skill_levels"
    __table_args__ = (UniqueConstraint("user_id", "skill_id", name="uq_user_skill"),)

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    skill_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("skills.id", ondelete="CASCADE"), nullable=False
    )
    level: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    aspiration_level: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    user: Mapped["User"] = relationship("User", back_populates="skill_levels")
    skill: Mapped["Skill"] = relationship("Skill", back_populates="levels")


# ── Jira ───────────────────────────────────────────────────────────────────────

class JiraIssue(Base):
    __tablename__ = "jira_issues"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    external_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    key: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, index=True)
    project_key: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    priority: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    issue_type: Mapped[str] = mapped_column(String(50), nullable=False)
    assignee_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reporter_username: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    labels: Mapped[Optional[list[str]]] = mapped_column(ARRAY(String), nullable=True)
    jira_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    jira_created_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    jira_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    raw_data: Mapped[Optional[str]] = mapped_column(EncryptedString, nullable=True)

    assignee: Mapped[Optional["User"]] = relationship("User", back_populates="assigned_issues")
    mr_links: Mapped[list["MRIssueLink"]] = relationship(
        "MRIssueLink", back_populates="issue", cascade="all, delete-orphan"
    )

    @property
    def linked_mrs(self) -> list["GitLabMR"]:
        """Merge requests linked to this issue (via MRIssueLink)."""
        return [link.mr for link in self.mr_links]


# ── GitLab MRs ─────────────────────────────────────────────────────────────────

class GitLabMR(Base):
    __tablename__ = "gitlab_mrs"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    external_id: Mapped[int] = mapped_column(Integer, nullable=False)  # GitLab MR IID
    project_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    project_name: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    state: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    author_username: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)
    assignee_usernames: Mapped[Optional[list[str]]] = mapped_column(ARRAY(String), nullable=True)
    reviewer_usernames: Mapped[Optional[list[str]]] = mapped_column(ARRAY(String), nullable=True)
    source_branch: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    target_branch: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    web_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    jira_issue_keys: Mapped[Optional[list[str]]] = mapped_column(ARRAY(String), nullable=True)
    review_age_hours: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    breach_threshold_hours: Mapped[float] = mapped_column(Float, nullable=False, default=24.0)
    breached: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    mr_created_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    mr_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    mr_merged_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    issue_links: Mapped[list["MRIssueLink"]] = relationship(
        "MRIssueLink", back_populates="mr", cascade="all, delete-orphan"
    )

    @property
    def linked_issues(self) -> list["JiraIssue"]:
        """Jira issues linked to this merge request (via MRIssueLink)."""
        return [link.issue for link in self.issue_links]


class MRIssueLink(Base):
    """Many-to-many link between GitLab MRs and Jira issues."""

    __tablename__ = "mr_issue_links"
    __table_args__ = (UniqueConstraint("mr_id", "issue_id", name="uq_mr_issue"),)

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    mr_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("gitlab_mrs.id", ondelete="CASCADE"), nullable=False
    )
    issue_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), ForeignKey("jira_issues.id", ondelete="CASCADE"), nullable=False
    )

    mr: Mapped["GitLabMR"] = relationship("GitLabMR", back_populates="issue_links")
    issue: Mapped["JiraIssue"] = relationship("JiraIssue", back_populates="mr_links")


# ── Connector Config ────────────────────────────────────────────────────────────

class ConnectorConfig(Base):
    __tablename__ = "connector_configs"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    connector_type: Mapped[str] = mapped_column(String(20), nullable=False)
    base_url: Mapped[str] = mapped_column(EncryptedString, nullable=False)
    token: Mapped[str] = mapped_column(EncryptedString, nullable=False)
    project_keys: Mapped[Optional[list[str]]] = mapped_column(ARRAY(String), nullable=True)
    project_ids: Mapped[Optional[list[int]]] = mapped_column(ARRAY(Integer), nullable=True)
    poll_interval_seconds: Mapped[int] = mapped_column(Integer, default=300)
    last_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    is_healthy: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


# ── Review Threshold (global config) ───────────────────────────────────────────

class ReviewThreshold(Base):
    __tablename__ = "review_thresholds"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    threshold_hours: Mapped[float] = mapped_column(Float, nullable=False, default=24.0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


# ── Audit Log ──────────────────────────────────────────────────────────────────

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    user_id: Mapped[Optional[str]] = mapped_column(
        UUID(as_uuid=False), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    resource_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)
