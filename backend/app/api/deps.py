"""Shared FastAPI dependencies.

Routers across the application (``app.dashboard``, ``app.issues``,
``app.merge_requests``, ``app.models.users``, ``app.models.skills``,
``app.core.config``, ``app.auth``) import authentication/database
dependencies from ``app.api.deps``. The concrete implementation lives in
``app.api.v1.deps`` alongside the rest of the v1 routing setup; this module
re-exports the public names so ``app.api.deps`` resolves for every consumer.
"""

from __future__ import annotations

from app.api.v1.deps import (
    CurrentUser,
    DB,
    get_current_user,
    require_role,
    write_audit_log,
)

__all__ = [
    "CurrentUser",
    "DB",
    "get_current_user",
    "require_role",
    "write_audit_log",
]
