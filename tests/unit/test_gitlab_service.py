from datetime import timedelta

import pytest

from app.models import JiraProject, WorkItem
from app.services.cache_service import CacheService
from app.services.gitlab_service import GitLabService, gitlab_source_id
from app.util import utcnow
from tests.helpers import FakeGitLabClient, make_memory_session, make_mr


@pytest.fixture()
def session():
    return make_memory_session()


def build_service(session, client=None, jira_url="https://jira.example.com", threshold=2):
    return GitLabService(
        session,
        cache_service=CacheService(session),
        client=client,
        jira_url=jira_url,
        review_threshold_days=threshold,
    )


def test_fetch_and_cache_round_trip(session):
    mrs = [make_mr(101), make_mr(102, title="Fix bug", review_status="Approved")]
    service = build_service(session, FakeGitLabClient(mrs))
    result = service.fetch_and_cache(1)
    assert result.success and result.item_count == 2

    cached = {mr.gitlab_id: mr for mr in service.list_merge_requests()}
    assert set(cached) == {101, 102}
    assert cached[101].title == "Add feature"
    assert cached[101].author_username == "alice"
    assert cached[101].target_branch == "main"
    assert cached[102].review_status == "Approved"


def test_fetch_failure_retains_cache(session):
    service = build_service(session, FakeGitLabClient([make_mr(101)]))
    service.fetch_and_cache(1)

    failing = build_service(session, FakeGitLabClient(fail=True))
    result = failing.fetch_and_cache(1)
    assert not result.success
    assert [mr.gitlab_id for mr in failing.list_merge_requests()] == [101]
    assert CacheService(session).consecutive_failure_count(gitlab_source_id(1)) == 1


def test_author_or_reviewer_filter(session):
    mrs = [
        make_mr(101, author_username="alice", reviewers=["bob"]),
        make_mr(102, author_username="carol", reviewers=["dave"]),
    ]
    service = build_service(session, FakeGitLabClient(mrs))
    service.fetch_and_cache(1)
    assert [mr.gitlab_id for mr in service.list_merge_requests("alice")] == [101]
    assert [mr.gitlab_id for mr in service.list_merge_requests("bob")] == [101]
    assert [mr.gitlab_id for mr in service.list_merge_requests("dave")] == [102]
    assert service.list_merge_requests("nobody") == []
    assert len(service.list_merge_requests()) == 2


def test_overdue_flag_respects_threshold(session):
    old = (utcnow() - timedelta(days=5)).isoformat()
    fresh = (utcnow() - timedelta(hours=6)).isoformat()
    mrs = [make_mr(101, created_at=old), make_mr(102, created_at=fresh)]
    service = build_service(session, FakeGitLabClient(mrs), threshold=2)
    service.fetch_and_cache(1)
    cached = {mr.gitlab_id: mr for mr in service.list_merge_requests()}
    assert cached[101].overdue is True
    assert cached[102].overdue is False


def test_ticket_links_extracted_and_resolved(session):
    session.add(JiraProject(project_key="PROJ", display_name="Project"))
    session.add(WorkItem(issue_key="PROJ-7", project_key="PROJ", summary="x", status="Open"))
    session.commit()
    mrs = [
        make_mr(
            101,
            title="PROJ-7 fix login",
            description="Also mentions PROJ-999 and PROJ-7 again",
            source_branch="feature/PROJ-7-login",
        ),
        make_mr(102, title="No ticket here", description="", source_branch="chore/misc"),
    ]
    service = build_service(session, FakeGitLabClient(mrs))
    service.fetch_and_cache(1)

    cached = {mr.gitlab_id: mr for mr in service.list_merge_requests()}
    links = {link.issue_key: link for link in cached[101].ticket_links}
    assert set(links) == {"PROJ-7", "PROJ-999"}  # deduplicated
    assert links["PROJ-7"].resolved is True
    assert links["PROJ-7"].url == "https://jira.example.com/browse/PROJ-7"
    assert links["PROJ-999"].resolved is False
    assert links["PROJ-999"].url is None
    assert cached[102].ticket_links == ()


def test_reads_never_call_the_client(session):
    client = FakeGitLabClient([make_mr(101)])
    service = build_service(session, client)
    service.fetch_and_cache(1)
    client.calls.clear()

    build_service(session, client).list_merge_requests()
    assert client.calls == []


def test_closed_mrs_dropped_on_refresh(session):
    service = build_service(session, FakeGitLabClient([make_mr(101), make_mr(102)]))
    service.fetch_and_cache(1)
    service = build_service(session, FakeGitLabClient([make_mr(102)]))
    service.fetch_and_cache(1)
    assert [mr.gitlab_id for mr in service.list_merge_requests()] == [102]
