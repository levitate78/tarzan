"""Seed default skill catalogue

Revision ID: 002
Revises: 001
Create Date: 2025-01-02 00:00:00
"""

from __future__ import annotations

import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


# (name, category) — category values must match SkillCategory enum values.
DEFAULT_SKILLS: list[tuple[str, str]] = [
    ("Python", "languages"),
    ("TypeScript", "languages"),
    ("JavaScript", "languages"),
    ("Go", "languages"),
    ("SQL", "languages"),
    ("FastAPI", "frameworks"),
    ("React", "frameworks"),
    ("NestJS", "frameworks"),
    ("Vue", "frameworks"),
    ("AWS", "cloud"),
    ("Azure", "cloud"),
    ("GCP", "cloud"),
    ("PostgreSQL", "databases"),
    ("Redis", "databases"),
    ("MongoDB", "databases"),
    ("Docker", "devops"),
    ("Kubernetes", "devops"),
    ("CI/CD", "devops"),
    ("Terraform", "devops"),
    ("Unit Testing", "testing"),
    ("End-to-End Testing", "testing"),
    ("Code Review", "soft_skills"),
    ("Mentoring", "soft_skills"),
    ("Technical Writing", "soft_skills"),
]


def upgrade() -> None:
    skills_table = sa.table(
        "skills",
        sa.column("id", UUID(as_uuid=False)),
        sa.column("name", sa.String),
        sa.column("category", sa.String),
        sa.column("description", sa.Text),
    )
    op.bulk_insert(
        skills_table,
        [
            {
                "id": str(uuid.uuid4()),
                "name": name,
                "category": category,
                "description": None,
            }
            for name, category in DEFAULT_SKILLS
        ],
    )


def downgrade() -> None:
    conn = op.get_bind()
    for name, _category in DEFAULT_SKILLS:
        conn.execute(sa.text("DELETE FROM skills WHERE name = :name"), {"name": name})
