"""Application configuration read from environment variables.

All environment-specific configuration is externalised (Requirement 12.3).
On startup, missing required values produce a descriptive structured log
line and a non-zero exit (Requirement 12.4).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

from werkzeug.security import generate_password_hash

from app.logging_setup import register_secret, setup_logging

logger = logging.getLogger(__name__)

REQUIRED_VARS = (
    "TARZAN_DB_KEY",
    "TARZAN_DATA_DIR",
    "TARZAN_SECRET_KEY",
    "TARZAN_ADMIN_USERNAME",
    "TARZAN_ADMIN_PASSWORD",
)


def _parse_bool(value: str | None, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Config:
    db_key: str
    data_dir: Path
    secret_key: str
    admin_username: str
    admin_password_hash: str
    db_path: Path
    https_enforce: bool = False
    allow_unencrypted_db: bool = False
    scheduler_enabled: bool = True
    testing: bool = False
    log_level: str = "INFO"
    session_lifetime_hours: int = 12
    extra: dict = field(default_factory=dict)

    @property
    def avatars_dir(self) -> Path:
        return self.data_dir / "avatars"

    @classmethod
    def from_env(cls, environ: dict | None = None) -> "Config":
        """Build a Config from the environment, exiting non-zero on missing
        required values (Requirement 12.4)."""
        setup_logging()
        env = os.environ if environ is None else environ

        missing = [name for name in REQUIRED_VARS if not env.get(name)]
        if missing:
            for name in missing:
                logger.error(
                    "Required configuration value is missing: %s. "
                    "Set this environment variable and restart.",
                    name,
                )
            raise SystemExit(1)

        db_key = env["TARZAN_DB_KEY"]
        admin_password = env["TARZAN_ADMIN_PASSWORD"]
        secret_key = env["TARZAN_SECRET_KEY"]
        # Ensure raw secrets can never leak into log output (Requirement 10.2).
        register_secret(db_key)
        register_secret(admin_password)
        register_secret(secret_key)

        data_dir = Path(env["TARZAN_DATA_DIR"])
        db_path = Path(env.get("TARZAN_DB_PATH") or (data_dir / "tarzan.db"))

        return cls(
            db_key=db_key,
            data_dir=data_dir,
            secret_key=secret_key,
            admin_username=env["TARZAN_ADMIN_USERNAME"],
            admin_password_hash=generate_password_hash(admin_password),
            db_path=db_path,
            https_enforce=_parse_bool(env.get("TARZAN_HTTPS_ENFORCE"), False),
            allow_unencrypted_db=_parse_bool(env.get("TARZAN_ALLOW_UNENCRYPTED_DB"), False),
            scheduler_enabled=not _parse_bool(env.get("TARZAN_DISABLE_SCHEDULER"), False),
            testing=_parse_bool(env.get("TARZAN_TESTING"), False),
            log_level=env.get("TARZAN_LOG_LEVEL", "INFO"),
        )
