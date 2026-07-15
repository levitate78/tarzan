"""Shared fixtures: app factory with a temp data dir, test client, DB session."""

from __future__ import annotations

import re

import pytest

from app import create_app
from app.config import Config

ADMIN_USERNAME = "manager"
ADMIN_PASSWORD = "correct-horse-battery"


def make_test_config(tmp_path, **overrides) -> Config:
    env = {
        "TARZAN_DB_KEY": "test-db-key-value",
        "TARZAN_DATA_DIR": str(tmp_path / "data"),
        "TARZAN_SECRET_KEY": "test-secret-key-value",
        "TARZAN_ADMIN_USERNAME": ADMIN_USERNAME,
        "TARZAN_ADMIN_PASSWORD": ADMIN_PASSWORD,
        "TARZAN_ALLOW_UNENCRYPTED_DB": "true",
        "TARZAN_DISABLE_SCHEDULER": "true",
        "TARZAN_TESTING": "true",
    }
    env.update(overrides)
    return Config.from_env(env)


@pytest.fixture()
def app(tmp_path):
    return create_app(make_test_config(tmp_path))


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def db_session(app):
    session = app.extensions["tarzan_session_factory"]()
    yield session
    session.close()


def extract_csrf_token(html: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match, "No CSRF token found in page"
    return match.group(1)


def login(client, username: str = ADMIN_USERNAME, password: str = ADMIN_PASSWORD):
    page = client.get("/auth/login")
    token = extract_csrf_token(page.get_data(as_text=True))
    return client.post(
        "/auth/login",
        data={"username": username, "password": password, "csrf_token": token},
        follow_redirects=False,
    )


def csrf_for(client, path: str) -> str:
    """Fetch a page and pull a CSRF token out of it."""
    page = client.get(path)
    return extract_csrf_token(page.get_data(as_text=True))


@pytest.fixture()
def logged_in_client(client):
    response = login(client)
    assert response.status_code == 302
    return client
