"""Startup smoke tests: config validation and health endpoint
(Requirements 12.4, 12.5)."""

from __future__ import annotations

import json
import logging

import pytest

from app import create_app
from app.config import REQUIRED_VARS, Config
from app.logging_setup import TarzanJsonFormatter
from tests.conftest import make_test_config


def full_env(tmp_path) -> dict:
    return {
        "TARZAN_DB_KEY": "key",
        "TARZAN_DATA_DIR": str(tmp_path),
        "TARZAN_SECRET_KEY": "secret",
        "TARZAN_ADMIN_USERNAME": "manager",
        "TARZAN_ADMIN_PASSWORD": "password",
        "TARZAN_ALLOW_UNENCRYPTED_DB": "true",
        "TARZAN_DISABLE_SCHEDULER": "true",
    }


@pytest.mark.parametrize("missing", REQUIRED_VARS)
def test_missing_required_var_exits_nonzero_and_names_it(tmp_path, caplog, missing):
    env = full_env(tmp_path)
    del env[missing]
    with caplog.at_level(logging.ERROR):
        with pytest.raises(SystemExit) as excinfo:
            Config.from_env(env)
    assert excinfo.value.code != 0
    assert any(missing in record.getMessage() for record in caplog.records)


def test_app_starts_and_health_returns_200(tmp_path):
    app = create_app(make_test_config(tmp_path))
    response = app.test_client().get("/health")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


def test_log_lines_are_structured_json():
    formatter = TarzanJsonFormatter()
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname=__file__, lineno=1,
        msg="hello world", args=(), exc_info=None,
    )
    parsed = json.loads(formatter.format(record))
    assert parsed["message"] == "hello world"
    assert parsed["severity"] == "INFO"
    assert "T" in parsed["timestamp"]  # ISO 8601


def test_cached_data_survives_restart(tmp_path):
    """Requirement 9.1: a restarted app serves previously cached data."""
    config = make_test_config(tmp_path)
    app = create_app(config)
    with app.app_context():
        session = app.extensions["tarzan_session_factory"]()
        from app.models import WorkItem

        session.add(
            WorkItem(issue_key="PROJ-1", project_key="PROJ", summary="cached", status="Open")
        )
        session.commit()
        session.close()
    app.extensions["tarzan_engine"].dispose()

    # Simulate a restart: brand new app instance over the same data dir.
    app2 = create_app(make_test_config(tmp_path))
    with app2.app_context():
        session = app2.extensions["tarzan_session_factory"]()
        from app.services.jira_service import JiraService

        items = JiraService(session).list_work_items()
        session.close()
    assert [item.issue_key for item in items] == ["PROJ-1"]
