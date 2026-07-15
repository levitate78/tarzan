"""Refresh bookkeeping for the local cache (Requirements 8.4-8.6, 9.3)."""

from __future__ import annotations

import logging
from datetime import timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.constants import STALENESS_FAILURE_THRESHOLD
from app.dtos import RefreshStatusDTO
from app.models import RefreshLog
from app.util import utcnow

logger = logging.getLogger(__name__)

REFRESH_LOG_RETENTION_DAYS = 30


class CacheService:
    def __init__(self, session: Session):
        self._session = session

    def record_refresh(self, source_id: str, success: bool, error: str | None = None) -> None:
        self._session.add(
            RefreshLog(
                source_id=source_id,
                success=success,
                error_message=error,
                attempted_at=utcnow(),
            )
        )
        self._session.commit()

    def get_last_refresh(self, source_id: str):
        """Datetime of the last *successful* refresh for a source, or None."""
        return self._session.execute(
            select(RefreshLog.attempted_at)
            .where(RefreshLog.source_id == source_id, RefreshLog.success.is_(True))
            .order_by(RefreshLog.attempted_at.desc(), RefreshLog.id.desc())
            .limit(1)
        ).scalar_one_or_none()

    def consecutive_failure_count(self, source_id: str) -> int:
        """Failures since the most recent success (Requirement 8.5)."""
        rows = self._session.execute(
            select(RefreshLog.success)
            .where(RefreshLog.source_id == source_id)
            .order_by(RefreshLog.attempted_at.desc(), RefreshLog.id.desc())
        ).scalars()
        count = 0
        for success in rows:
            if success:
                break
            count += 1
        return count

    def prune_old_entries(self) -> int:
        """Delete refresh log rows older than the retention window (startup)."""
        cutoff = utcnow() - timedelta(days=REFRESH_LOG_RETENTION_DAYS)
        result = self._session.execute(
            delete(RefreshLog).where(RefreshLog.attempted_at < cutoff)
        )
        self._session.commit()
        return result.rowcount or 0

    def get_refresh_status(
        self, source_id: str, display_name: str, interval_minutes: int
    ) -> RefreshStatusDTO:
        """Aggregate status for a dashboard: last success, failure streak,
        and whether the data is older than one refresh cycle (Req 9.3)."""
        last_success = self.get_last_refresh(source_id)
        failures = self.consecutive_failure_count(source_id)
        stale = bool(
            last_success is not None
            and utcnow() - last_success > timedelta(minutes=interval_minutes)
        )
        return RefreshStatusDTO(
            source_id=source_id,
            display_name=display_name,
            last_success=last_success,
            consecutive_failures=failures,
            stale=stale,
        )

    @staticmethod
    def is_failing(status: RefreshStatusDTO) -> bool:
        return status.consecutive_failures >= STALENESS_FAILURE_THRESHOLD
