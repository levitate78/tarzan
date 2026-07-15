import pytest

from app.exceptions import NotFoundError, ReassignError, ReassignTimeoutError
from app.services.cache_service import CacheService
from app.services.jira_service import JiraService, jira_source_id
from tests.helpers import FakeJiraClient, add_member, make_issue, make_memory_session


@pytest.fixture()
def session():
    return make_memory_session()


def build_service(session, client=None):
    return JiraService(session, cache_service=CacheService(session), client=client)


def test_fetch_and_cache_round_trip(session):
    issues = [make_issue("PROJ-1"), make_issue("PROJ-2", status="Blocked", priority="Low")]
    service = build_service(session, FakeJiraClient(issues))
    result = service.fetch_and_cache("PROJ")
    assert result.success and result.item_count == 2

    items = {item.issue_key: item for item in service.list_work_items()}
    assert set(items) == {"PROJ-1", "PROJ-2"}
    item = items["PROJ-1"]
    assert item.summary == "Do the thing"
    assert item.assignee_display_name == "Alice Smith"
    assert item.status == "In Progress"
    assert item.priority == "High"


def test_fetch_failure_retains_cache_and_records_failure(session):
    service = build_service(session, FakeJiraClient([make_issue("PROJ-1")]))
    service.fetch_and_cache("PROJ")

    failing = build_service(session, FakeJiraClient(fail=True))
    result = failing.fetch_and_cache("PROJ")
    assert not result.success

    items = failing.list_work_items()
    assert [item.issue_key for item in items] == ["PROJ-1"]
    cache = CacheService(session)
    assert cache.consecutive_failure_count(jira_source_id("PROJ")) == 1


def test_removed_issues_are_dropped_on_successful_refresh(session):
    service = build_service(session, FakeJiraClient([make_issue("PROJ-1"), make_issue("PROJ-2")]))
    service.fetch_and_cache("PROJ")
    service = build_service(session, FakeJiraClient([make_issue("PROJ-2")]))
    service.fetch_and_cache("PROJ")
    assert [item.issue_key for item in service.list_work_items()] == ["PROJ-2"]


def test_list_excludes_done_statuses(session):
    issues = [
        make_issue("PROJ-1", status="Done"),
        make_issue("PROJ-2", status="Closed"),
        make_issue("PROJ-3", status="Cancelled"),
        make_issue("PROJ-4", status="In Progress"),
    ]
    service = build_service(session, FakeJiraClient(issues))
    service.fetch_and_cache("PROJ")
    assert [item.issue_key for item in service.list_work_items()] == ["PROJ-4"]


def test_assignee_filter_matches_account_id_and_display_name(session):
    issues = [
        make_issue("PROJ-1", assignee_account_id="acc-1", assignee_display_name="Alice"),
        make_issue("PROJ-2", assignee_account_id="acc-2", assignee_display_name="Bob"),
    ]
    service = build_service(session, FakeJiraClient(issues))
    service.fetch_and_cache("PROJ")
    assert [i.issue_key for i in service.list_work_items(assignee="Alice")] == ["PROJ-1"]
    assert [i.issue_key for i in service.list_work_items(assignee="acc-2")] == ["PROJ-2"]
    assert service.list_work_items(assignee="nobody") == []


def test_blocked_and_in_review_flags(session):
    issues = [
        make_issue("PROJ-1", status="Blocked"),
        make_issue(
            "PROJ-2",
            status="Open",
            linked_issues=[{"key": "PROJ-9", "type": "is blocked by"}],
        ),
        make_issue("PROJ-3", status="In Review"),
        make_issue("PROJ-4", status="Open"),
    ]
    service = build_service(session, FakeJiraClient(issues))
    service.fetch_and_cache("PROJ")
    items = {item.issue_key: item for item in service.list_work_items()}
    assert items["PROJ-1"].is_blocked and not items["PROJ-1"].is_in_review
    assert items["PROJ-2"].is_blocked
    assert items["PROJ-3"].is_in_review and not items["PROJ-3"].is_blocked
    assert not items["PROJ-4"].is_blocked and not items["PROJ-4"].is_in_review


def test_detail_view_contains_all_sections(session):
    issue = make_issue(
        "PROJ-1",
        description="Long description",
        labels=["backend", "urgent"],
        comments=[{"author": "Bob", "body": "LGTM", "created": "2026-07-01"}],
        linked_issues=[{"key": "PROJ-2", "type": "relates to"}],
    )
    service = build_service(session, FakeJiraClient([issue]))
    service.fetch_and_cache("PROJ")
    detail = service.get_work_item("PROJ-1")
    assert detail.description == "Long description"
    assert detail.labels == ("backend", "urgent")
    assert detail.comments[0]["body"] == "LGTM"
    assert detail.linked_issues[0]["key"] == "PROJ-2"


def test_reads_never_call_the_client(session):
    client = FakeJiraClient([make_issue("PROJ-1")])
    service = build_service(session, client)
    service.fetch_and_cache("PROJ")
    client.calls.clear()

    read_only = build_service(session, client)
    read_only.list_work_items()
    read_only.get_work_item("PROJ-1")
    assert client.calls == []


def test_reassign_success_updates_cache(session):
    add_member(session, username="bob", name="Bob Jones", jira_account_id="acc-bob")
    client = FakeJiraClient([make_issue("PROJ-1")])
    service = build_service(session, client)
    service.fetch_and_cache("PROJ")

    result = service.reassign_work_item("PROJ-1", "acc-bob")
    assert result.new_assignee_account_id == "acc-bob"
    detail = service.get_work_item("PROJ-1")
    assert detail.assignee_account_id == "acc-bob"
    assert detail.assignee_display_name == "Bob Jones"
    # Other fields untouched.
    assert detail.summary == "Do the thing"
    assert detail.status == "In Progress"


def test_reassign_failure_leaves_cache_unchanged(session):
    add_member(session, username="bob", name="Bob", jira_account_id="acc-bob")
    service = build_service(session, FakeJiraClient([make_issue("PROJ-1")]))
    service.fetch_and_cache("PROJ")

    failing = build_service(session, FakeJiraClient(fail=True))
    with pytest.raises(ReassignError):
        failing.reassign_work_item("PROJ-1", "acc-bob")
    detail = failing.get_work_item("PROJ-1")
    assert detail.assignee_account_id == "acc-1"


def test_reassign_timeout_raises_timeout_error_and_leaves_cache(session):
    add_member(session, username="bob", name="Bob", jira_account_id="acc-bob")
    service = build_service(session, FakeJiraClient([make_issue("PROJ-1")]))
    service.fetch_and_cache("PROJ")

    timing_out = build_service(session, FakeJiraClient(timeout=True))
    with pytest.raises(ReassignTimeoutError):
        timing_out.reassign_work_item("PROJ-1", "acc-bob")
    assert timing_out.get_work_item("PROJ-1").assignee_account_id == "acc-1"


def test_reassign_to_non_team_member_rejected(session):
    service = build_service(session, FakeJiraClient([make_issue("PROJ-1")]))
    service.fetch_and_cache("PROJ")
    with pytest.raises(ReassignError):
        service.reassign_work_item("PROJ-1", "stranger")


def test_reassign_unknown_item_raises_not_found(session):
    add_member(session, username="bob", name="Bob")
    service = build_service(session, FakeJiraClient())
    with pytest.raises(NotFoundError):
        service.reassign_work_item("PROJ-404", "bob")
