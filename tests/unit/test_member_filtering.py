"""Dashboard member filtering resolves configured external identities
(Requirements 4.9 and 6.7)."""

from __future__ import annotations

import pytest

from tests.conftest import csrf_for
from tests.helpers import FakeGitLabClient, FakeJiraClient, make_issue, make_mr


def create_profile(client, username, name, jira_account_id="", gitlab_username=""):
    token = csrf_for(client, "/profiles/new")
    client.post(
        "/profiles/new",
        data={
            "name": name,
            "username": username,
            "jira_account_id": jira_account_id,
            "gitlab_username": gitlab_username,
            "csrf_token": token,
        },
    )


@pytest.fixture()
def filtering_client(logged_in_client, monkeypatch):
    """A logged-in client with two profiles and cached Jira/GitLab data.

    alice has both external identities configured; bob has neither. The
    cached Jira display name for alice deliberately differs from her profile
    name, so a match proves account-ID filtering rather than name equality.
    """
    client = logged_in_client
    create_profile(
        client, "alice", "Alice Smith", jira_account_id="acc-alice", gitlab_username="alice-gl"
    )
    create_profile(client, "bob", "Bob Jones")

    token = csrf_for(client, "/settings/")
    client.post(
        "/settings/projects/jira",
        data={"project_key": "PROJ", "display_name": "Backend", "csrf_token": token},
    )
    client.post(
        "/settings/projects/gitlab",
        data={"gitlab_project_id": "101", "display_name": "Repo", "csrf_token": token},
    )

    jira_fake = FakeJiraClient(
        issues=[
            make_issue(
                "PROJ-1",
                assignee_account_id="acc-alice",
                assignee_display_name="Alice In Jira",
            ),
            make_issue(
                "PROJ-2",
                assignee_account_id="acc-bob",
                assignee_display_name="Bob Jones",
            ),
        ]
    )
    gitlab_fake = FakeGitLabClient(
        merge_requests=[
            make_mr(
                gitlab_id=1,
                title="Alice export MR",
                author_username="alice-gl",
                reviewers=["carol-gl"],
            ),
            make_mr(gitlab_id=2, title="Bob cleanup MR", author_username="bob", reviewers=[]),
        ]
    )
    monkeypatch.setattr("app.blueprints.jira.build_jira_client", lambda: jira_fake)
    monkeypatch.setattr("app.blueprints.gitlab.build_gitlab_client", lambda: gitlab_fake)
    client.post("/jira/refresh", data={"csrf_token": token})
    client.post("/gitlab/refresh", data={"csrf_token": token})
    return client


# -- Jira work items ----------------------------------------------------------


def test_jira_filter_by_username_matches_account_id(filtering_client):
    body = filtering_client.get("/jira/?assignee=alice").get_data(as_text=True)
    assert "PROJ-1" in body
    assert "PROJ-2" not in body
    assert "no Jira account ID configured" not in body


def test_jira_filter_falls_back_to_name_with_notice(filtering_client):
    body = filtering_client.get("/jira/?assignee=bob").get_data(as_text=True)
    assert "PROJ-2" in body
    assert "PROJ-1" not in body
    assert "Bob Jones has no Jira account ID configured" in body


def test_jira_legacy_filter_values_still_match(filtering_client):
    by_account_id = filtering_client.get("/jira/?assignee=acc-alice").get_data(as_text=True)
    assert "PROJ-1" in by_account_id and "PROJ-2" not in by_account_id
    by_display_name = filtering_client.get("/jira/?assignee=Alice In Jira").get_data(
        as_text=True
    )
    assert "PROJ-1" in by_display_name and "PROJ-2" not in by_display_name


def test_jira_dropdown_options_carry_usernames(filtering_client):
    body = filtering_client.get("/jira/?assignee=alice").get_data(as_text=True)
    assert '<option value="alice" selected>Alice Smith</option>' in body
    assert 'value="bob"' in body


# -- GitLab merge requests -----------------------------------------------------


def test_gitlab_filter_by_username_matches_gitlab_username(filtering_client):
    body = filtering_client.get("/gitlab/?member=alice").get_data(as_text=True)
    assert "Alice export MR" in body
    assert "Bob cleanup MR" not in body
    assert "no GitLab username configured" not in body


def test_gitlab_filter_falls_back_to_username_with_notice(filtering_client):
    body = filtering_client.get("/gitlab/?member=bob").get_data(as_text=True)
    assert "Bob cleanup MR" in body
    assert "Alice export MR" not in body
    assert "Bob Jones has no GitLab username configured" in body


def test_gitlab_legacy_filter_values_still_match(filtering_client):
    body = filtering_client.get("/gitlab/?member=alice-gl").get_data(as_text=True)
    assert "Alice export MR" in body
    assert "Bob cleanup MR" not in body


def test_gitlab_dropdown_options_carry_usernames(filtering_client):
    body = filtering_client.get("/gitlab/?member=alice").get_data(as_text=True)
    assert '<option value="alice" selected>Alice Smith</option>' in body
