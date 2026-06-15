from __future__ import annotations

from functools import lru_cache
from typing import Literal, Optional

from pydantic import AnyHttpUrl, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ── App ───────────────────────────────────────────────────────────────────
    APP_NAME: str = "Tarzan"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: Literal["development", "staging", "production"] = "development"
    DEBUG: bool = False

    # ── API ───────────────────────────────────────────────────────────────────
    API_V1_PREFIX: str = "/api/v1"
    ALLOWED_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:5173"]

    # ── Database ──────────────────────────────────────────────────────────────
    DATABASE_URL: str = "postgresql+asyncpg://tarzan:tarzan@localhost:5432/tarzan"
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 20

    # ── Redis ─────────────────────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379/0"
    CACHE_TTL_SECONDS: int = 300

    # ── Security / JWT ────────────────────────────────────────────────────────
    SECRET_KEY: str  # Must be set in environment — min 32 chars
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    BCRYPT_ROUNDS: int = 12

    # ── Encryption (AES-256-GCM for sensitive DB columns) ─────────────────────
    FIELD_ENCRYPTION_KEY: str  # 32-byte base64url-encoded key

    # ── Rate limiting ─────────────────────────────────────────────────────────
    RATE_LIMIT_PER_MINUTE: int = 120

    # ── Review threshold ──────────────────────────────────────────────────────
    DEFAULT_REVIEW_THRESHOLD_HOURS: float = 24.0

    # ── Worker ────────────────────────────────────────────────────────────────
    WORKER_POLL_INTERVAL_SECONDS: int = 300

    # ── Initial admin bootstrap ─────────────────────────────────────────────────
    # If set (and no users exist yet), an initial admin account is created on
    # startup. Leave unset in production once the first admin has been created.
    ADMIN_USERNAME: Optional[str] = None
    ADMIN_PASSWORD: Optional[str] = None
    ADMIN_EMAIL: Optional[str] = None
    ADMIN_FULL_NAME: str = "Administrator"

    @field_validator("SECRET_KEY")
    @classmethod
    def secret_key_length(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError("SECRET_KEY must be at least 32 characters")
        return v

    @field_validator("FIELD_ENCRYPTION_KEY")
    @classmethod
    def encryption_key_length(cls, v: str) -> str:
        import base64

        try:
            decoded = base64.urlsafe_b64decode(v + "==")
            if len(decoded) < 32:
                raise ValueError("Decoded key must be at least 32 bytes")
        except Exception as exc:
            raise ValueError("FIELD_ENCRYPTION_KEY must be base64url-encoded") from exc
        return v

    @field_validator("ADMIN_PASSWORD")
    @classmethod
    def admin_password_length(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and len(v) < 12:
            raise ValueError("ADMIN_PASSWORD must be at least 12 characters")
        return v

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
