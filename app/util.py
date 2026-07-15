"""Small shared helpers."""

from __future__ import annotations

from datetime import datetime, timezone


def utcnow() -> datetime:
    """Naive UTC now — all persisted datetimes are naive UTC for consistent
    comparison with values read back from SQLite."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def parse_iso_datetime(value: str | None) -> datetime | None:
    """Parse an ISO 8601 string (with or without Z/offset) to naive UTC."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed
