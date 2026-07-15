"""SQLAlchemy models for all tables (see the ER diagram in the design doc).

All tables live in a single SQLCipher-encrypted database file, which also
serves as the persistent cache for external API data.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.util import utcnow


class Base(DeclarativeBase):
    pass


class TeamMember(Base):
    __tablename__ = "team_member"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    avatar_path: Mapped[str | None] = mapped_column(String(500))
    jira_account_id: Mapped[str | None] = mapped_column(String(200))
    gitlab_username: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    skills: Mapped[list["SkillsMatrix"]] = relationship(
        back_populates="member", cascade="all, delete-orphan"
    )


class Skill(Base):
    __tablename__ = "skill"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    deprecated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    matrix_entries: Mapped[list["SkillsMatrix"]] = relationship(back_populates="skill")


class SkillsMatrix(Base):
    __tablename__ = "skills_matrix"
    __table_args__ = (UniqueConstraint("member_id", "skill_id", name="uq_member_skill"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    member_id: Mapped[int] = mapped_column(ForeignKey("team_member.id"), nullable=False)
    skill_id: Mapped[int] = mapped_column(ForeignKey("skill.id"), nullable=False)
    current_level: Mapped[str] = mapped_column(String(20), nullable=False)
    aspiration_level: Mapped[str | None] = mapped_column(String(20))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    member: Mapped[TeamMember] = relationship(back_populates="skills")
    skill: Mapped[Skill] = relationship(back_populates="matrix_entries")


class WorkItem(Base):
    __tablename__ = "work_item"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    issue_key: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    project_key: Mapped[str] = mapped_column(String(50), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    assignee_account_id: Mapped[str | None] = mapped_column(String(200))
    assignee_display_name: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    priority: Mapped[str | None] = mapped_column(String(100))
    description_json: Mapped[str | None] = mapped_column(Text)
    labels_json: Mapped[str | None] = mapped_column(Text)
    linked_issues_json: Mapped[str | None] = mapped_column(Text)
    comments_json: Mapped[str | None] = mapped_column(Text)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class MergeRequest(Base):
    __tablename__ = "merge_request"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    gitlab_id: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    project_id: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False, default="")
    author_username: Mapped[str | None] = mapped_column(String(200))
    target_branch: Mapped[str | None] = mapped_column(String(300))
    source_branch: Mapped[str | None] = mapped_column(String(300))
    review_status: Mapped[str] = mapped_column(String(50), nullable=False, default="Awaiting Review")
    description: Mapped[str | None] = mapped_column(Text)
    reviewers_json: Mapped[str | None] = mapped_column(Text)
    web_url: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime | None] = mapped_column(DateTime)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    ticket_links: Mapped[list["TicketLink"]] = relationship(
        back_populates="merge_request", cascade="all, delete-orphan"
    )


class TicketLink(Base):
    __tablename__ = "ticket_link"
    __table_args__ = (UniqueConstraint("mr_id", "issue_key", name="uq_mr_issue"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    mr_id: Mapped[int] = mapped_column(ForeignKey("merge_request.id"), nullable=False)
    issue_key: Mapped[str] = mapped_column(String(50), nullable=False)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    merge_request: Mapped[MergeRequest] = relationship(back_populates="ticket_links")


class JiraProject(Base):
    __tablename__ = "jira_project"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_key: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class GitLabProject(Base):
    __tablename__ = "gitlab_project"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    gitlab_project_id: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Credential(Base):
    __tablename__ = "credential"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    encrypted_value: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)


class RefreshLog(Base):
    __tablename__ = "refresh_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    attempted_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class ConfigEntry(Base):
    __tablename__ = "config"

    key: Mapped[str] = mapped_column(String(200), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)


class UserSession(Base):
    """Server-side session record enabling real session invalidation
    (Requirement 10.5)."""

    __tablename__ = "user_session"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    username: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime)
