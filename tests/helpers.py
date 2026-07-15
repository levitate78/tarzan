"""Test helpers: pristine in-memory database sessions and fake API clients."""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.exceptions import GitLabClientError, JiraClientError
from app.models import Base, TeamMember


def make_memory_session() -> Session:
    """A fresh in-memory SQLite session with the full schema — used by
    property tests so each Hypothesis example starts from pristine state."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def add_member(session, username: str = "alice", name: str = "Alice Smith", **kwargs):
    member = TeamMember(username=username, name=name, **kwargs)
    session.add(member)
    session.commit()
    return member


class FakeJiraClient:
    """In-memory JiraClient double recording every call."""

    def __init__(self, issues=None, fail=False, timeout=False):
        self.issues = issues or []
        self.fail = fail
        self.timeout = timeout
        self.calls = []

    def search_issues(self, jql):
        self.calls.append(("search_issues", jql))
        if self.timeout:
            raise JiraClientError("Jira search timed out")
        if self.fail:
            raise JiraClientError("Jira returned HTTP 500")
        return list(self.issues)

    def get_issue(self, issue_key):
        self.calls.append(("get_issue", issue_key))
        for issue in self.issues:
            if issue["key"] == issue_key:
                return issue
        raise JiraClientError(f"Issue {issue_key} not found")

    def update_assignee(self, issue_key, account_id):
        self.calls.append(("update_assignee", issue_key, account_id))
        if self.timeout:
            raise JiraClientError("Jira request timed out")
        if self.fail:
            raise JiraClientError("Jira returned HTTP 403")


class FakeGitLabClient:
    """In-memory GitLabClient double recording every call."""

    def __init__(self, merge_requests=None, fail=False):
        self.merge_requests = merge_requests or []
        self.fail = fail
        self.calls = []

    def list_merge_requests(self, project_id, state="opened"):
        self.calls.append(("list_merge_requests", project_id, state))
        if self.fail:
            raise GitLabClientError("GitLab returned HTTP 502")
        return list(self.merge_requests)


def make_issue(key="PROJ-1", **overrides) -> dict:
    issue = {
        "key": key,
        "summary": "Do the thing",
        "assignee_account_id": "acc-1",
        "assignee_display_name": "Alice Smith",
        "status": "In Progress",
        "priority": "High",
        "description": "Details",
        "labels": ["backend"],
        "comments": [],
        "linked_issues": [],
    }
    issue.update(overrides)
    return issue


def make_mr(gitlab_id=101, **overrides) -> dict:
    mr = {
        "id": gitlab_id,
        "iid": gitlab_id,
        "project_id": 1,
        "title": "Add feature",
        "author_username": "alice",
        "source_branch": "feature/thing",
        "target_branch": "main",
        "description": "",
        "created_at": "2026-07-01T10:00:00Z",
        "web_url": "https://gitlab.example.com/mr/101",
        "reviewers": ["bob"],
        "review_status": "Awaiting Review",
    }
    mr.update(overrides)
    return mr
