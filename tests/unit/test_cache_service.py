from datetime import timedelta

import pytest

from app.models import RefreshLog
from app.services.cache_service import CacheService
from app.util import utcnow
from tests.helpers import make_memory_session


@pytest.fixture()
def session():
    return make_memory_session()


@pytest.fixture()
def cache(session):
    return CacheService(session)


def test_last_refresh_returns_latest_success_only(cache):
    assert cache.get_last_refresh("jira:PROJ") is None
    cache.record_refresh("jira:PROJ", success=True)
    first = cache.get_last_refresh("jira:PROJ")
    cache.record_refresh("jira:PROJ", success=False, error="boom")
    assert cache.get_last_refresh("jira:PROJ") == first


def test_consecutive_failures_reset_on_success(cache):
    source = "gitlab:1"
    assert cache.consecutive_failure_count(source) == 0
    for _ in range(3):
        cache.record_refresh(source, success=False, error="x")
    assert cache.consecutive_failure_count(source) == 3
    cache.record_refresh(source, success=True)
    assert cache.consecutive_failure_count(source) == 0


def test_failure_count_is_per_source(cache):
    cache.record_refresh("jira:A", success=False, error="x")
    cache.record_refresh("jira:B", success=True)
    assert cache.consecutive_failure_count("jira:A") == 1
    assert cache.consecutive_failure_count("jira:B") == 0


def test_prune_removes_only_old_entries(session, cache):
    session.add(
        RefreshLog(
            source_id="jira:OLD",
            success=True,
            attempted_at=utcnow() - timedelta(days=45),
        )
    )
    session.commit()
    cache.record_refresh("jira:NEW", success=True)
    removed = cache.prune_old_entries()
    assert removed == 1
    assert cache.get_last_refresh("jira:OLD") is None
    assert cache.get_last_refresh("jira:NEW") is not None


def test_refresh_status_staleness(cache):
    cache.record_refresh("jira:PROJ", success=True)
    status = cache.get_refresh_status("jira:PROJ", "Project", interval_minutes=15)
    assert status.stale is False
    assert status.failing is False

    # Simulate an old success followed by repeated failures.
    for _ in range(3):
        cache.record_refresh("jira:PROJ", success=False, error="x")
    status = cache.get_refresh_status("jira:PROJ", "Project", interval_minutes=15)
    assert status.consecutive_failures == 3
    assert status.failing is True
