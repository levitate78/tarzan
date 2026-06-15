"""Shared pytest configuration.

``app.config.Settings`` requires ``SECRET_KEY`` and ``FIELD_ENCRYPTION_KEY``
to be set, and several modules instantiate ``Settings`` at import time
(e.g. ``app.database``). These defaults let the test suite import the
application without requiring a real ``.env`` file or live database.
"""

from __future__ import annotations

import base64
import os

os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("SECRET_KEY", "test-only-secret-key-not-for-production-use")
os.environ.setdefault("FIELD_ENCRYPTION_KEY", base64.urlsafe_b64encode(os.urandom(32)).decode())
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://tarzan:tarzan@localhost:5432/tarzan_test")
