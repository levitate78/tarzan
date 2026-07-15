"""HTTP-level tests: authentication, access control, CSRF, HTTPS
enforcement, escaping, and dashboard empty states."""

from __future__ import annotations

from app import create_app
from tests.conftest import csrf_for, login, make_test_config

PROTECTED_ROUTES = [
    "/profiles/",
    "/profiles/new",
    "/skills/catalogue",
    "/skills/dashboard",
    "/jira/",
    "/gitlab/",
    "/settings/",
]


def test_health_is_public(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


def test_protected_routes_return_401_when_unauthenticated(client):
    for route in PROTECTED_ROUTES:
        response = client.get(route)
        assert response.status_code == 401, route
        body = response.get_data(as_text=True)
        assert "log in" in body.lower()


def test_login_with_wrong_password_fails(client):
    response = login(client, password="wrong")
    assert response.status_code == 200
    assert "Invalid username or password" in response.get_data(as_text=True)


def test_login_and_logout_invalidates_session(client):
    assert login(client).status_code == 302
    assert client.get("/profiles/").status_code == 200

    token = csrf_for(client, "/profiles/")
    response = client.post("/auth/logout", data={"csrf_token": token})
    assert response.status_code == 302
    # Session is invalidated server-side: same cookie no longer works.
    assert client.get("/profiles/").status_code == 401


def test_post_without_csrf_token_rejected(logged_in_client):
    response = logged_in_client.post("/skills/catalogue", data={"name": "Python"})
    assert response.status_code == 400


def test_create_profile_flow(logged_in_client):
    token = csrf_for(logged_in_client, "/profiles/new")
    response = logged_in_client.post(
        "/profiles/new",
        data={"name": "Alice Smith", "username": "alice", "csrf_token": token},
        follow_redirects=True,
    )
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "Alice Smith" in body
    assert "alice" in body


def test_duplicate_username_shows_error(logged_in_client):
    token = csrf_for(logged_in_client, "/profiles/new")
    data = {"name": "Alice", "username": "alice", "csrf_token": token}
    logged_in_client.post("/profiles/new", data=data)
    response = logged_in_client.post("/profiles/new", data=data)
    assert "already in use" in response.get_data(as_text=True)


def test_missing_name_shows_field_specific_error(logged_in_client):
    token = csrf_for(logged_in_client, "/profiles/new")
    response = logged_in_client.post(
        "/profiles/new",
        data={"name": "  ", "username": "alice", "csrf_token": token},
    )
    assert "name field is required" in response.get_data(as_text=True)


def test_html_output_is_escaped(logged_in_client):
    token = csrf_for(logged_in_client, "/profiles/new")
    hostile = '<script>alert("x")</script>'
    logged_in_client.post(
        "/profiles/new",
        data={"name": hostile, "username": "eve", "csrf_token": token},
    )
    response = logged_in_client.get("/profiles/")
    body = response.get_data(as_text=True)
    assert "<script>alert" not in body
    assert "&lt;script&gt;" in body


def test_dashboards_render_empty_state(logged_in_client):
    for route, marker in [
        ("/jira/", "No work item data"),
        ("/gitlab/", "No merge request data"),
    ]:
        body = logged_in_client.get(route).get_data(as_text=True)
        assert marker in body, route


def test_settings_validation_rejects_out_of_range(logged_in_client):
    token = csrf_for(logged_in_client, "/settings/")
    response = logged_in_client.post(
        "/settings/refresh-interval",
        data={"refresh_interval": "0", "csrf_token": token},
        follow_redirects=True,
    )
    assert "between 1 and 60" in response.get_data(as_text=True)
    response = logged_in_client.post(
        "/settings/review-threshold",
        data={"review_threshold": "31", "csrf_token": token},
        follow_redirects=True,
    )
    assert "between 1 and 30" in response.get_data(as_text=True)


def test_settings_accepts_valid_values(logged_in_client):
    token = csrf_for(logged_in_client, "/settings/")
    response = logged_in_client.post(
        "/settings/review-threshold",
        data={"review_threshold": "5", "csrf_token": token},
        follow_redirects=True,
    )
    assert "Review threshold set to 5" in response.get_data(as_text=True)


def test_https_enforcement_redirects_plain_http(tmp_path):
    app = create_app(make_test_config(tmp_path, TARZAN_HTTPS_ENFORCE="true"))
    client = app.test_client()
    response = client.get("/auth/login", base_url="http://tarzan.example.com")
    assert response.status_code == 301
    assert response.headers["Location"].startswith("https://tarzan.example.com")


def test_https_enforcement_allows_localhost(tmp_path):
    app = create_app(make_test_config(tmp_path, TARZAN_HTTPS_ENFORCE="true"))
    client = app.test_client()
    response = client.get("/health", base_url="http://localhost")
    assert response.status_code == 200


def test_invalid_issue_key_is_404(logged_in_client):
    assert logged_in_client.get("/jira/not-a-key").status_code == 404


def test_unknown_work_item_redirects_with_error(logged_in_client):
    response = logged_in_client.get("/jira/PROJ-999", follow_redirects=True)
    assert "not in the cache" in response.get_data(as_text=True)
