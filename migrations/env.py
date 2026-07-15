"""Alembic environment using the SQLCipher-aware engine from app.crypto."""

from __future__ import annotations

from alembic import context

from app.config import Config
from app.crypto import build_engine
from app.models import Base

target_metadata = Base.metadata


def run_migrations_online() -> None:
    config = Config.from_env()
    engine = build_engine(config)

    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


run_migrations_online()
