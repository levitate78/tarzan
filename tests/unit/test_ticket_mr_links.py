"""Ticket-side Jira–GitLab linking: merge requests referencing a work item
by its issue key in the title (or description/branch) are listed on the
work item detail view."""

from __future__ import annotations

import pytest

from app.models import JiraProject
from app.services.cache_service import CacheService
from app.services.gitlab_service import GitLabService
from app.services.jira_service import JiraService
from tests.helpers import (
    FakeGitLabClient,
    FakeJiraClient,
    make_issue,
    make_memory_session,
    make_mr,
)


@pytest.fixture()
def session():
    return make_memory_session()


def seed_session(session, mrs):
    session.add(JiraProject(project_key="PROJ", display_name="Project"))
    session.commit()
    jira = JiraService(
        session,
        cache_service=CacheService(session),
        client=FakeJiraClient([make_issue("PROJ-1"), make_issue("PROJ-2")]),
    )
    assert jira.fetch_and_cache("PROJ").success
    gitlab = GitLabService(
        session,
        cache_service=CacheService(session),
        client=FakeGitLabClient(mrs),
        jira_url="https://jira.example.com",
    )
    assert gitlab.fetch_and_cache(1).success
    return gitlab


def test_merge_requests_listed_for_referenced_issue(session):
    gitlab = seed_session(
        session,
        [
            make_mr(101, title="PROJ-1 fix the thing"),
            make_mr(102, title="Unrelated tidy-up"),
            make_mr(103, title="PROJ-2 other work"),
        ],
    )
    linked = gitlab.list_merge_requests_for_issue("PROJ-1")
    assert [mr.gitlab_id for mr in linked] == [101]
    assert linked[0].ticket_links[0].issue_key == "PROJ-1"
    assert linked[0].ticket_links[0].url == "https://jira.example.com/browse/PROJ-1"

    assert gitlab.list_merge_requests_for_issue("PROJ-9") == []


def test_one_merge_request_can_reference_multiple_issues(session):
    gitlab = seed_session(session, [make_mr(101, title="PROJ-1 PROJ-2 combined fix")])
    assert [mr.gitlab_id for mr in gitlab.list_merge_requests_for_issue("PROJ-1")] == [101]
    assert [mr.gitlab_id for mr in gitlab.list_merge_requests_for_issue("PROJ-2")] == [101]


def test_detail_page_lists_linked_merge_requests(app, logged_in_client):
    session = app.extensions["tarzan_session_factory"]()
    try:
        seed_session(session, [make_mr(101, title="PROJ-1 fix the thing")])
    finally:
        session.close()
    page = logged_in_client.get("/jira/PROJ-1").get_data(as_text=True)
    assert "PROJ-1 fix the thing" in page
    assert "Awaiting Review" in page

    other = logged_in_client.get("/jira/PROJ-2").get_data(as_text=True)
    assert "No merge requests reference this work item." in other
