"""Manual data refresh routes for Jira and GitLab (Requirement 14)."""

from __future__ import annotations

from tests.conftest import csrf_for, extract_csrf_token
from tests.helpers import FakeGitLabClient, FakeJiraClient, make_issue, make_mr


def add_jira_project(client, key="PROJ"):
    token = csrf_for(client, "/settings/")
    client.post(
        "/settings/projects/jira",
        data={"project_key": key, "display_name": "Backend", "csrf_token": token},
    )


def add_gitlab_project(client, project_id=101):
    token = csrf_for(client, "/settings/")
    client.post(
        "/settings/projects/gitlab",
        data={
            "gitlab_project_id": str(project_id),
            "display_name": "Backend repo",
            "csrf_token": token,
        },
    )


def post_refresh(client, path):
    token = csrf_for(client, "/settings/")
    return client.post(path, data={"csrf_token": token}, follow_redirects=True)


def test_refresh_requires_authentication(client):
    login_page = client.get("/auth/login").get_data(as_text=True)
    token = extract_csrf_token(login_page)
    for path in ("/jira/refresh", "/gitlab/refresh"):
        response = client.post(path, data={"csrf_token": token})
        assert response.status_code == 401, path


def test_refresh_with_no_projects_points_at_settings(logged_in_client):
    body = post_refresh(logged_in_client, "/jira/refresh").get_data(as_text=True)
    assert "No Jira projects are configured" in body
    body = post_refresh(logged_in_client, "/gitlab/refresh").get_data(as_text=True)
    assert "No GitLab projects are configured" in body


def test_refresh_without_credentials_points_at_settings(logged_in_client):
    add_jira_project(logged_in_client)
    add_gitlab_project(logged_in_client)
    body = post_refresh(logged_in_client, "/jira/refresh").get_data(as_text=True)
    assert "Jira is not configured" in body
    body = post_refresh(logged_in_client, "/gitlab/refresh").get_data(as_text=True)
    assert "GitLab is not configured" in body


def test_jira_manual_refresh_caches_items_and_reports_counts(logged_in_client, monkeypatch):
    add_jira_project(logged_in_client)
    fake = FakeJiraClient(issues=[make_issue(key="PROJ-1"), make_issue(key="PROJ-2")])
    monkeypatch.setattr("app.blueprints.jira.build_jira_client", lambda: fake)

    body = post_refresh(logged_in_client, "/jira/refresh").get_data(as_text=True)

    assert "Refreshed 1 Jira project(s): 2 work item(s) fetched." in body
    dashboard = logged_in_client.get("/jira/").get_data(as_text=True)
    assert "PROJ-1" in dashboard
    assert "PROJ-2" in dashboard


def test_jira_manual_refresh_failure_names_project_and_keeps_cache(
    logged_in_client, monkeypatch
):
    add_jira_project(logged_in_client)
    working = FakeJiraClient(issues=[make_issue(key="PROJ-1")])
    monkeypatch.setattr("app.blueprints.jira.build_jira_client", lambda: working)
    post_refresh(logged_in_client, "/jira/refresh")

    failing = FakeJiraClient(fail=True)
    monkeypatch.setattr("app.blueprints.jira.build_jira_client", lambda: failing)
    body = post_refresh(logged_in_client, "/jira/refresh").get_data(as_text=True)

    assert "Refresh failed for: Backend" in body
    assert "Existing cached data was kept." in body
    dashboard = logged_in_client.get("/jira/").get_data(as_text=True)
    assert "PROJ-1" in dashboard  # Requirement 14.5: cache retained


def test_gitlab_manual_refresh_caches_items_and_reports_counts(
    logged_in_client, monkeypatch
):
    add_gitlab_project(logged_in_client)
    fake = FakeGitLabClient(merge_requests=[make_mr(gitlab_id=7, title="Add exports")])
    monkeypatch.setattr("app.blueprints.gitlab.build_gitlab_client", lambda: fake)

    body = post_refresh(logged_in_client, "/gitlab/refresh").get_data(as_text=True)

    assert "Refreshed 1 GitLab project(s): 1 merge request(s) fetched." in body
    dashboard = logged_in_client.get("/gitlab/").get_data(as_text=True)
    assert "Add exports" in dashboard


def test_gitlab_manual_refresh_failure_names_project_and_keeps_cache(
    logged_in_client, monkeypatch
):
    add_gitlab_project(logged_in_client)
    working = FakeGitLabClient(merge_requests=[make_mr(gitlab_id=7, title="Add exports")])
    monkeypatch.setattr("app.blueprints.gitlab.build_gitlab_client", lambda: working)
    post_refresh(logged_in_client, "/gitlab/refresh")

    failing = FakeGitLabClient(fail=True)
    monkeypatch.setattr("app.blueprints.gitlab.build_gitlab_client", lambda: failing)
    body = post_refresh(logged_in_client, "/gitlab/refresh").get_data(as_text=True)

    assert "Refresh failed for: Backend repo" in body
    dashboard = logged_in_client.get("/gitlab/").get_data(as_text=True)
    assert "Add exports" in dashboard  # Requirement 14.5: cache retained


def test_dashboards_render_refresh_buttons(logged_in_client):
    jira_page = logged_in_client.get("/jira/").get_data(as_text=True)
    assert "/jira/refresh" in jira_page
    gitlab_page = logged_in_client.get("/gitlab/").get_data(as_text=True)
    assert "/gitlab/refresh" in gitlab_page
