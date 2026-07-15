"""Per-request database session management."""

from __future__ import annotations

from flask import current_app, g
from sqlalchemy.orm import Session


def get_session() -> Session:
    """Return the request-scoped SQLAlchemy session, creating it on demand."""
    if "db_session" not in g:
        g.db_session = current_app.extensions["tarzan_session_factory"]()
    return g.db_session


def close_session(_exception=None) -> None:
    session = g.pop("db_session", None)
    if session is not None:
        session.close()
