"""Initial schema

Revision ID: 001
Revises:
Create Date: 2025-01-01 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, ARRAY

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("username", sa.String(50), nullable=False, unique=True),
        sa.Column("email", sa.Text, nullable=False),             # encrypted
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("avatar_url", sa.Text, nullable=True),
        sa.Column("gitlab_username", sa.String(100), nullable=True),
        sa.Column("jira_username", sa.String(100), nullable=True),
        sa.Column("role", sa.String(20), nullable=False, server_default="member"),
        sa.Column("hashed_password", sa.Text, nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                  onupdate=sa.func.now()),
    )
    op.create_index("ix_users_username", "users", ["username"])
    op.create_index("ix_users_gitlab_username", "users", ["gitlab_username"])
    op.create_index("ix_users_jira_username", "users", ["jira_username"])

    op.create_table(
        "skills",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "skill_levels",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=False),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("skill_id", UUID(as_uuid=False),
                  sa.ForeignKey("skills.id", ondelete="CASCADE"), nullable=False),
        sa.Column("level", sa.Integer, nullable=False, server_default="0"),
        sa.Column("aspiration_level", sa.Integer, nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "skill_id", name="uq_user_skill"),
    )

    op.create_table(
        "jira_issues",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("external_id", sa.String(100), nullable=False),
        sa.Column("key", sa.String(50), nullable=False, unique=True),
        sa.Column("project_key", sa.String(20), nullable=False),
        sa.Column("summary", sa.Text, nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("priority", sa.String(20), nullable=True),
        sa.Column("issue_type", sa.String(50), nullable=False),
        sa.Column("assignee_id", UUID(as_uuid=False),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reporter_username", sa.String(100), nullable=True),
        sa.Column("labels", ARRAY(sa.String), nullable=True),
        sa.Column("jira_url", sa.Text, nullable=True),
        sa.Column("jira_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("jira_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("synced_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("raw_data", sa.Text, nullable=True),             # encrypted
    )
    op.create_index("ix_jira_issues_key", "jira_issues", ["key"])
    op.create_index("ix_jira_issues_project_key", "jira_issues", ["project_key"])
    op.create_index("ix_jira_issues_external_id", "jira_issues", ["external_id"])

    op.create_table(
        "gitlab_mrs",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("external_id", sa.Integer, nullable=False),
        sa.Column("project_id", sa.Integer, nullable=False),
        sa.Column("project_name", sa.String(255), nullable=False),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("author_username", sa.String(100), nullable=True),
        sa.Column("assignee_usernames", ARRAY(sa.String), nullable=True),
        sa.Column("reviewer_usernames", ARRAY(sa.String), nullable=True),
        sa.Column("source_branch", sa.String(255), nullable=True),
        sa.Column("target_branch", sa.String(255), nullable=True),
        sa.Column("web_url", sa.Text, nullable=True),
        sa.Column("jira_issue_keys", ARRAY(sa.String), nullable=True),
        sa.Column("review_age_hours", sa.Float, nullable=False, server_default="0"),
        sa.Column("breach_threshold_hours", sa.Float, nullable=False, server_default="24"),
        sa.Column("breached", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("mr_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("mr_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("mr_merged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("synced_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_gitlab_mrs_project_id", "gitlab_mrs", ["project_id"])
    op.create_index("ix_gitlab_mrs_state", "gitlab_mrs", ["state"])
    op.create_index("ix_gitlab_mrs_author", "gitlab_mrs", ["author_username"])

    op.create_table(
        "mr_issue_links",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("mr_id", UUID(as_uuid=False),
                  sa.ForeignKey("gitlab_mrs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("issue_id", UUID(as_uuid=False),
                  sa.ForeignKey("jira_issues.id", ondelete="CASCADE"), nullable=False),
        sa.UniqueConstraint("mr_id", "issue_id", name="uq_mr_issue"),
    )

    op.create_table(
        "connector_configs",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("connector_type", sa.String(20), nullable=False),
        sa.Column("base_url", sa.Text, nullable=False),           # encrypted
        sa.Column("token", sa.Text, nullable=False),              # encrypted
        sa.Column("project_keys", ARRAY(sa.String), nullable=True),
        sa.Column("project_ids", ARRAY(sa.Integer), nullable=True),
        sa.Column("poll_interval_seconds", sa.Integer, nullable=False, server_default="300"),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_healthy", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_table(
        "review_thresholds",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("threshold_hours", sa.Float, nullable=False, server_default="24"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    # Seed default
    op.execute("INSERT INTO review_thresholds (id, threshold_hours) VALUES (1, 24)")

    op.create_table(
        "audit_logs",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=False),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("resource_type", sa.String(50), nullable=True),
        sa.Column("resource_id", sa.String(100), nullable=True),
        sa.Column("details", sa.Text, nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("review_thresholds")
    op.drop_table("connector_configs")
    op.drop_table("mr_issue_links")
    op.drop_table("gitlab_mrs")
    op.drop_table("jira_issues")
    op.drop_table("skill_levels")
    op.drop_table("skills")
    op.drop_table("users")