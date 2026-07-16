"""Work item filtering (status, component, parent epic), blocked-time
tracking, per-project component fetch filters, and the epics listing."""

from __future__ import annotations

import json

import pytest

from app.models import JiraProject
from app.services.cache_service import CacheService
from app.services.jira_service import JiraService
from tests.conftest import csrf_for
from tests.helpers import FakeJiraClient, make_issue, make_memory_session


@pytest.fixture()
def session():
    return make_memory_session()


def build_service(session, client=None):
    return JiraService(session, cache_service=CacheService(session), client=client)


def cache_issues(session, issues, project_key="PROJ"):
    service = build_service(session, FakeJiraClient(issues))
    result = service.fetch_and_cache(project_key)
    assert result.success
    return build_service(session)


# -- Status / component / epic filters --------------------------------------


def test_status_filter_is_case_insensitive(session):
    service = cache_issues(
        session,
        [make_issue("PROJ-1", status="In Progress"), make_issue("PROJ-2", status="Blocked")],
    )
    assert [i.issue_key for i in service.list_work_items(status="in progress")] == ["PROJ-1"]
    assert [i.issue_key for i in service.list_work_items(status="Blocked")] == ["PROJ-2"]
    assert service.list_work_items(status="Missing") == []


def test_component_filter_matches_any_component(session):
    service = cache_issues(
        session,
        [
            make_issue("PROJ-1", components=["Backend", "API"]),
            make_issue("PROJ-2", components=["Frontend"]),
            make_issue("PROJ-3", components=[]),
        ],
    )
    assert [i.issue_key for i in service.list_work_items(component="api")] == ["PROJ-1"]
    assert [i.issue_key for i in service.list_work_items(component="Frontend")] == ["PROJ-2"]
    assert service.list_work_items(component="Database") == []


def test_epic_filter_matches_parent_epic_key(session):
    service = cache_issues(
        session,
        [
            make_issue("PROJ-1", parent_epic_key="PROJ-100"),
            make_issue("PROJ-2", parent_epic_key="PROJ-200"),
            make_issue("PROJ-3"),
        ],
    )
    assert [i.issue_key for i in service.list_work_items(epic="proj-100")] == ["PROJ-1"]
    assert service.list_work_items(epic="PROJ-999") == []


def test_filters_combine_with_assignee(session):
    service = cache_issues(
        session,
        [
            make_issue("PROJ-1", components=["API"], assignee_display_name="Alice"),
            make_issue("PROJ-2", components=["API"], assignee_display_name="Bob"),
        ],
    )
    items = service.list_work_items(assignee="Alice", component="API")
    assert [i.issue_key for i in items] == ["PROJ-1"]


def test_filter_options_lists_distinct_values(session):
    service = cache_issues(
        session,
        [
            make_issue("PROJ-100", issue_type="Epic", summary="Big epic"),
            make_issue("PROJ-1", status="Blocked", components=["API"], parent_epic_key="PROJ-100"),
            make_issue("PROJ-2", components=["API", "Backend"], parent_epic_key="PROJ-999"),
        ],
    )
    options = service.list_filter_options()
    assert set(options.statuses) == {"In Progress", "Blocked"}
    assert options.components == ("API", "Backend")
    # Cached epics carry their summary; epics only referenced as a parent
    # still appear (without a summary).
    assert dict(options.epics) == {"PROJ-100": "Big epic", "PROJ-999": None}


# -- Blocked-time tracking ---------------------------------------------------


def test_blocked_since_set_and_preserved_across_refreshes(session):
    service = cache_issues(session, [make_issue("PROJ-1", status="Blocked")])
    first = service.list_work_items(blocked_only=True)[0]
    assert first.is_blocked and first.blocked_since is not None

    # A later refresh with the item still blocked keeps the original time.
    service = cache_issues(session, [make_issue("PROJ-1", status="Blocked")])
    again = service.list_work_items(blocked_only=True)[0]
    assert again.blocked_since == first.blocked_since


def test_blocked_since_cleared_when_unblocked(session):
    cache_issues(session, [make_issue("PROJ-1", status="Blocked")])
    service = cache_issues(session, [make_issue("PROJ-1", status="In Progress")])
    item = service.list_work_items()[0]
    assert not item.is_blocked and item.blocked_since is None
    assert service.list_work_items(blocked_only=True) == []


def test_blocked_only_includes_blocking_links(session):
    service = cache_issues(
        session,
        [
            make_issue(
                "PROJ-1",
                linked_issues=[{"key": "PROJ-9", "type": "is blocked by"}],
            ),
            make_issue("PROJ-2"),
        ],
    )
    blocked = service.list_work_items(blocked_only=True)
    assert [i.issue_key for i in blocked] == ["PROJ-1"]
    assert blocked[0].blocked_since is not None


# -- Per-project component fetch filter (Settings) ---------------------------


def test_fetch_jql_unrestricted_without_component_filter(session):
    client = FakeJiraClient([make_issue("PROJ-1")])
    build_service(session, client).fetch_and_cache("PROJ")
    assert client.calls == [("search_issues", 'project = "PROJ" ORDER BY updated DESC')]


def test_fetch_jql_restricted_to_configured_components(session):
    session.add(
        JiraProject(
            project_key="PROJ",
            display_name="Project",
            components_json=json.dumps(["Backend", "API"]),
        )
    )
    session.commit()
    client = FakeJiraClient([make_issue("PROJ-1")])
    build_service(session, client).fetch_and_cache("PROJ")
    assert client.calls == [
        (
            "search_issues",
            'project = "PROJ" AND component in ("Backend", "API") ORDER BY updated DESC',
        )
    ]


# -- Epics listing -----------------------------------------------------------


def epic_fixture_issues():
    return [
        make_issue("PROJ-100", issue_type="Epic", summary="Checkout", fix_versions=["1.0"]),
        make_issue("PROJ-200", issue_type="Epic", summary="Search"),
        make_issue("PROJ-300", issue_type="Epic", summary="Old", status="Done"),
        make_issue("PROJ-1", parent_epic_key="PROJ-100", status="Done"),
        make_issue("PROJ-2", parent_epic_key="PROJ-100", status="Blocked"),
        make_issue("PROJ-3", parent_epic_key="PROJ-200", fix_versions=["2.0"]),
    ]


def test_list_epics_reports_child_progress(session):
    service = cache_issues(session, epic_fixture_issues())
    epics = {epic.issue_key: epic for epic in service.list_epics()}
    # Done epics are not "being worked on".
    assert set(epics) == {"PROJ-100", "PROJ-200"}
    checkout = epics["PROJ-100"]
    assert checkout.child_total == 2
    assert checkout.child_done == 1
    assert checkout.child_blocked == 1
    assert checkout.fix_versions == ("1.0",)


def test_list_epics_filters_by_fix_version_of_epic_or_children(session):
    service = cache_issues(session, epic_fixture_issues())
    assert [e.issue_key for e in service.list_epics(fix_version="1.0")] == ["PROJ-100"]
    # PROJ-200 has no fix version itself but a child targeting 2.0.
    assert [e.issue_key for e in service.list_epics(fix_version="2.0")] == ["PROJ-200"]
    assert service.list_epics(fix_version="9.9") == []


def test_list_fix_versions_is_distinct_and_sorted(session):
    service = cache_issues(
        session,
        [
            make_issue("PROJ-1", fix_versions=["2.0", "1.0"]),
            make_issue("PROJ-2", fix_versions=["1.0"]),
        ],
    )
    assert service.list_fix_versions() == ["1.0", "2.0"]


# -- Routes ------------------------------------------------------------------


def seed_app_cache(app, issues, project_key="PROJ"):
    session = app.extensions["tarzan_session_factory"]()
    try:
        service = JiraService(session, cache_service=CacheService(session),
                              client=FakeJiraClient(issues))
        assert service.fetch_and_cache(project_key).success
    finally:
        session.close()


def test_dashboard_filters_render_and_apply(app, logged_in_client):
    seed_app_cache(
        app,
        [
            make_issue("PROJ-1", components=["API"], status="Blocked"),
            make_issue("PROJ-2", components=["Frontend"]),
        ],
    )
    page = logged_in_client.get("/jira/?component=API").get_data(as_text=True)
    assert "PROJ-1" in page and "PROJ-2" not in page

    page = logged_in_client.get("/jira/?status=Blocked").get_data(as_text=True)
    assert "PROJ-1" in page and "PROJ-2" not in page


def test_blocked_dashboard_shows_time_blocked_and_priority(app, logged_in_client):
    seed_app_cache(
        app,
        [
            make_issue("PROJ-1", status="Blocked", priority="Critical"),
            make_issue("PROJ-2", status="In Progress"),
        ],
    )
    page = logged_in_client.get("/jira/blocked").get_data(as_text=True)
    assert "PROJ-1" in page and "PROJ-2" not in page
    assert "Critical" in page
    assert "less than an hour" in page


def test_blocked_dashboard_filters_by_component(app, logged_in_client):
    seed_app_cache(
        app,
        [
            make_issue("PROJ-1", status="Blocked", components=["API"]),
            make_issue("PROJ-2", status="Blocked", components=["Frontend"]),
        ],
    )
    page = logged_in_client.get("/jira/blocked?component=Frontend").get_data(as_text=True)
    assert "PROJ-2" in page and "PROJ-1" not in page


def test_epics_dashboard_renders_and_filters(app, logged_in_client):
    seed_app_cache(app, epic_fixture_issues())
    page = logged_in_client.get("/jira/epics").get_data(as_text=True)
    assert "PROJ-100" in page and "PROJ-200" in page and "PROJ-300" not in page
    assert "1 of 2 child item(s) done" in page

    filtered = logged_in_client.get("/jira/epics?fix_version=1.0").get_data(as_text=True)
    assert "PROJ-100" in filtered and "PROJ-200" not in filtered


def test_settings_configures_project_component_filter(logged_in_client):
    token = csrf_for(logged_in_client, "/settings/")
    response = logged_in_client.post(
        "/settings/projects/jira",
        data={
            "project_key": "proj",
            "display_name": "Project",
            "components": "Backend, API, backend",
            "csrf_token": token,
        },
        follow_redirects=True,
    )
    page = response.get_data(as_text=True)
    # Duplicates are dropped case-insensitively; the filter is displayed.
    assert "Backend, API" in page


def test_settings_rejects_component_with_quotes(logged_in_client):
    token = csrf_for(logged_in_client, "/settings/")
    response = logged_in_client.post(
        "/settings/projects/jira",
        data={
            "project_key": "PROJ",
            "components": 'Bad"Name',
            "csrf_token": token,
        },
        follow_redirects=True,
    )
    page = response.get_data(as_text=True)
    assert "cannot contain double quotes" in page
