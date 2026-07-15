"""Structured JSON logging on stdout with secret scrubbing.

Every log line carries at minimum: timestamp (ISO 8601), severity, message
(Requirement 12.5). A scrubbing filter guarantees registered secret values
never appear in log output (Requirement 10.2).
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone

try:  # python-json-logger >= 3
    from pythonjsonlogger.json import JsonFormatter
except ImportError:  # python-json-logger 2.x
    from pythonjsonlogger.jsonlogger import JsonFormatter

REDACTED = "[REDACTED]"


class SecretRegistry:
    """Process-wide registry of secret values that must never be logged."""

    # Values shorter than this are not registered: redacting 1-3 character
    # substrings would mangle unrelated log text while providing no real
    # protection (they appear everywhere by chance).
    MIN_SECRET_LENGTH = 4

    _secrets: set[str] = set()

    @classmethod
    def register(cls, value: str | None) -> None:
        if value and len(value) >= cls.MIN_SECRET_LENGTH:
            cls._secrets.add(value)

    @classmethod
    def scrub(cls, text: str) -> str:
        for secret in cls._secrets:
            if secret in text:
                text = text.replace(secret, REDACTED)
        return text


def register_secret(value: str | None) -> None:
    """Register a secret value so the log filter redacts it everywhere."""
    SecretRegistry.register(value)


class SecretScrubbingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        record.msg = SecretRegistry.scrub(message)
        record.args = ()
        return True


class TarzanJsonFormatter(JsonFormatter):
    def add_fields(self, log_record, record, message_dict):
        super().add_fields(log_record, record, message_dict)
        log_record["timestamp"] = datetime.now(timezone.utc).isoformat()
        log_record["severity"] = record.levelname
        log_record["message"] = SecretRegistry.scrub(log_record.get("message") or "")


def setup_logging(level: int = logging.INFO) -> None:
    """Configure the root logger once; safe to call repeatedly."""
    root = logging.getLogger()
    if any(getattr(h, "_tarzan_handler", False) for h in root.handlers):
        return
    handler = logging.StreamHandler(sys.stdout)
    handler._tarzan_handler = True
    handler.setFormatter(TarzanJsonFormatter())
    handler.addFilter(SecretScrubbingFilter())
    root.addHandler(handler)
    root.setLevel(level)
