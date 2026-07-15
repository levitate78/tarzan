"""Property tests for cache bookkeeping, validation ranges, and persistence
(design Properties 22, 26, 27, 28)."""

from __future__ import annotations

import tempfile
from datetime import datetime
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.constants import STALENESS_FAILURE_THRESHOLD
from app.exceptions import ValidationError
from app.models import Base, RefreshLog, WorkItem
from app.services.cache_service import CacheService
from app.services.config_service import ConfigService
from app.services.jira_service import JiraService
from tests.helpers import make_memory_session


# Feature: team-dashboard, Property 22: Review threshold / interval validation
@given(value=st.integers(min_value=-1000, max_value=1000))
@settings(max_examples=100)
def test_review_threshold_and_interval_validation(value):
    config = ConfigService(make_memory_session())
    if 1 <= value <= 30:
        assert config.set_review_threshold_days(value) == value
        assert config.get_review_threshold_days() == value
    else:
        with pytest.raises(ValidationError):
            config.set_review_threshold_days(value)
    if 1 <= value <= 60:
        assert config.set_refresh_interval_minutes(value) == value
        assert config.get_refresh_interval_minutes() == value
    else:
        with pytest.raises(ValidationError):
            config.set_refresh_interval_minutes(value)


# Feature: team-dashboard, Property 26: Consecutive failure count triggers staleness
@given(
    failures=st.integers(min_value=0, max_value=8),
    success_after=st.booleans(),
)
@settings(max_examples=100)
def test_consecutive_failure_count(failures, success_after):
    cache = CacheService(make_memory_session())
    cache.record_refresh("jira:PROJ", success=True)  # baseline success
    for _ in range(failures):
        cache.record_refresh("jira:PROJ", success=False, error="x")
    if success_after:
        cache.record_refresh("jira:PROJ", success=True)
        assert cache.consecutive_failure_count("jira:PROJ") == 0
        status = cache.get_refresh_status("jira:PROJ", "Project", 15)
        assert status.failing is False
    else:
        assert cache.consecutive_failure_count("jira:PROJ") == failures
        status = cache.get_refresh_status("jira:PROJ", "Project", 15)
        assert status.failing is (failures >= STALENESS_FAILURE_THRESHOLD)


refresh_events = st.lists(
    st.tuples(
        st.datetimes(min_value=datetime(2020, 1, 1), max_value=datetime(2030, 1, 1)),
        st.booleans(),
    ),
    min_size=1,
    max_size=20,
)


# Feature: team-dashboard, Property 27: Last refresh timestamp round-trip
@given(events=refresh_events)
@settings(max_examples=100)
def test_last_refresh_returns_latest_success(events):
    session = make_memory_session()
    cache = CacheService(session)
    for attempted_at, success in events:
        session.add(
            RefreshLog(source_id="jira:PROJ", success=success, attempted_at=attempted_at)
        )
    session.commit()
    successes = [attempted_at for attempted_at, success in events if success]
    expected = max(successes) if successes else None
    assert cache.get_last_refresh("jira:PROJ") == expected


work_item_rows = st.lists(
    st.tuples(
        st.integers(min_value=1, max_value=999_999),  # issue number
        st.text(min_size=1, max_size=40),  # summary
        st.sampled_from(["Open", "In Progress", "Blocked", "In Review"]),
        st.sampled_from(["Low", "Medium", "High", None]),
    ),
    max_size=8,
    unique_by=lambda row: row[0],
)


# Feature: team-dashboard, Property 28: Cache persistence across restart simulation
@given(rows=work_item_rows)
@settings(max_examples=50, deadline=None)  # file-backed DB setup per example
def test_cache_survives_connection_restart(rows):
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "cache.db"
        url = f"sqlite:///{db_path.as_posix()}"

        engine = create_engine(url)
        Base.metadata.create_all(engine)
        session = sessionmaker(bind=engine)()
        for number, summary, status, priority in rows:
            session.add(
                WorkItem(
                    issue_key=f"PROJ-{number}",
                    project_key="PROJ",
                    summary=summary,
                    status=status,
                    priority=priority,
                )
            )
        session.commit()
        session.close()
        engine.dispose()  # simulate process shutdown

        engine2 = create_engine(url)
        session2 = sessionmaker(bind=engine2)()
        items = {
            item.issue_key: item
            for item in JiraService(session2).list_work_items(include_done=True)
        }
        session2.close()
        engine2.dispose()

        assert len(items) == len(rows)
        for number, summary, status, priority in rows:
            item = items[f"PROJ-{number}"]
            assert item.summary == summary
            assert item.status == status
            assert item.priority == priority
