"""Runtime configuration stored in the CONFIG table (refresh interval,
review threshold, external instance URLs, status mappings)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.constants import (
    CONFIG_GITLAB_URL,
    CONFIG_IN_REVIEW_STATUSES,
    CONFIG_JIRA_URL,
    CONFIG_REFRESH_INTERVAL,
    CONFIG_REVIEW_THRESHOLD,
    DEFAULT_IN_REVIEW_STATUSES,
    DEFAULT_REFRESH_INTERVAL_MINUTES,
    DEFAULT_REVIEW_THRESHOLD_DAYS,
    REFRESH_INTERVAL_RANGE,
    REVIEW_THRESHOLD_RANGE,
)
from app.exceptions import ValidationError
from app.models import ConfigEntry


class ConfigService:
    def __init__(self, session: Session):
        self._session = session

    def get_value(self, key: str, default: str | None = None) -> str | None:
        row = self._session.get(ConfigEntry, key)
        return row.value if row is not None else default

    def set_value(self, key: str, value: str) -> None:
        row = self._session.get(ConfigEntry, key)
        if row is None:
            self._session.add(ConfigEntry(key=key, value=value))
        else:
            row.value = value
        self._session.commit()

    # -- Typed accessors -------------------------------------------------

    def get_refresh_interval_minutes(self) -> int:
        return self._get_int(CONFIG_REFRESH_INTERVAL, DEFAULT_REFRESH_INTERVAL_MINUTES)

    def set_refresh_interval_minutes(self, value) -> int:
        interval = self._validate_int_range(
            value, REFRESH_INTERVAL_RANGE, "refresh interval", "minutes"
        )
        self.set_value(CONFIG_REFRESH_INTERVAL, str(interval))
        return interval

    def get_review_threshold_days(self) -> int:
        return self._get_int(CONFIG_REVIEW_THRESHOLD, DEFAULT_REVIEW_THRESHOLD_DAYS)

    def set_review_threshold_days(self, value) -> int:
        threshold = self._validate_int_range(
            value, REVIEW_THRESHOLD_RANGE, "review threshold", "days"
        )
        self.set_value(CONFIG_REVIEW_THRESHOLD, str(threshold))
        return threshold

    def get_jira_url(self) -> str | None:
        return self.get_value(CONFIG_JIRA_URL)

    def set_jira_url(self, value: str) -> None:
        self.set_value(CONFIG_JIRA_URL, value.strip().rstrip("/"))

    def get_gitlab_url(self) -> str | None:
        return self.get_value(CONFIG_GITLAB_URL)

    def set_gitlab_url(self, value: str) -> None:
        self.set_value(CONFIG_GITLAB_URL, value.strip().rstrip("/"))

    def get_in_review_statuses(self) -> set[str]:
        raw = self.get_value(CONFIG_IN_REVIEW_STATUSES, DEFAULT_IN_REVIEW_STATUSES) or ""
        return {status.strip().lower() for status in raw.split(",") if status.strip()}

    # -- Internals -------------------------------------------------------

    def _get_int(self, key: str, default: int) -> int:
        raw = self.get_value(key)
        try:
            return int(raw) if raw is not None else default
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _validate_int_range(value, valid_range: tuple[int, int], label: str, unit: str) -> int:
        low, high = valid_range
        try:
            parsed = int(str(value).strip())
        except (TypeError, ValueError):
            raise ValidationError(
                f"The {label} must be a whole number of {unit} between {low} and {high}.",
                field=label,
            ) from None
        if not low <= parsed <= high:
            raise ValidationError(
                f"The {label} must be between {low} and {high} {unit}.", field=label
            )
        return parsed
