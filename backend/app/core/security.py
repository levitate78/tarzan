"""Password hashing and JWT helpers.

Several modules (``app.api.v1.deps``, ``app.auth``, ``app.models.users``)
import these helpers from ``app.core.security``. The concrete
implementation lives in ``app.security``; this module re-exports it so both
import paths resolve to the same implementation.
"""

from __future__ import annotations

from app.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)

__all__ = [
    "create_access_token",
    "decode_access_token",
    "hash_password",
    "verify_password",
]
