"""Jira filtering, blocked tracking, epics, component filters, ticket skills.

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-16

Adds the work item fields backing the status/component/epic filters, the
blocked-since timestamp for the blocked dashboard, fix versions and issue
type for the epics dashboard, the per-project component filter, and the
work_item_skill link table.
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("work_item", sa.Column("issue_type", sa.String(100), nullable=True))
    op.add_column("work_item", sa.Column("parent_epic_key", sa.String(50), nullable=True))
    op.add_column("work_item", sa.Column("components_json", sa.Text(), nullable=True))
    op.add_column("work_item", sa.Column("fix_versions_json", sa.Text(), nullable=True))
    op.add_column("work_item", sa.Column("blocked_since", sa.DateTime(), nullable=True))
    op.add_column("jira_project", sa.Column("components_json", sa.Text(), nullable=True))
    op.create_table(
        "work_item_skill",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("issue_key", sa.String(50), nullable=False),
        sa.Column("skill_id", sa.Integer(), sa.ForeignKey("skill.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("issue_key", "skill_id", name="uq_issue_skill"),
    )
    op.create_index(
        "ix_work_item_skill_issue_key", "work_item_skill", ["issue_key"]
    )


def downgrade() -> None:
    op.drop_index("ix_work_item_skill_issue_key", table_name="work_item_skill")
    op.drop_table("work_item_skill")
    op.drop_column("jira_project", "components_json")
    op.drop_column("work_item", "blocked_since")
    op.drop_column("work_item", "fix_versions_json")
    op.drop_column("work_item", "components_json")
    op.drop_column("work_item", "parent_epic_key")
    op.drop_column("work_item", "issue_type")
