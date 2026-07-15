"""Initial schema: all Tarzan tables.

Revision ID: 0001
Revises:
Create Date: 2026-07-15

Creates the full schema from the current model metadata. This is the first
migration of a fresh application, so building it from `Base.metadata` is
equivalent to enumerating every `op.create_table` call while staying exactly
in sync with `app/models.py`.
"""

from alembic import op

from app.models import Base

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
