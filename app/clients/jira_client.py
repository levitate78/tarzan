"""Thin wrapper around the `jira` PyPI library.

Handles authentication, pagination, and timeouts, and raises the typed
JiraClientError instead of leaking library exceptions to the service layer.
Returned values are plain dicts with normalised fields.
"""

from __future__ import annotations

import logging

from app.exceptions import JiraClientError

logger = logging.getLogger(__name__)

_SEARCH_FIELDS = (
    "summary,assignee,status,priority,description,labels,issuelinks,comment,"
    "issuetype,parent,components,fixVersions"
)
_PAGE_SIZE = 50


class JiraClient:
    def __init__(self, server: str, token: str, timeout_seconds: int = 10):
        self._server = server.rstrip("/")
        self._timeout = timeout_seconds
        try:
            from jira import JIRA

            self._jira = JIRA(
                server=self._server,
                token_auth=token,
                timeout=timeout_seconds,
                max_retries=0,
            )
        except Exception as exc:  # noqa: BLE001 - normalise all library errors
            raise JiraClientError(f"Could not connect to Jira: {type(exc).__name__}") from exc

    def search_issues(self, jql: str) -> list[dict]:
        """Run a JQL search, following pagination, returning normalised dicts."""
        issues: list[dict] = []
        start_at = 0
        try:
            while True:
                page = self._jira.search_issues(
                    jql, startAt=start_at, maxResults=_PAGE_SIZE, fields=_SEARCH_FIELDS
                )
                issues.extend(self._normalise_issue(issue) for issue in page)
                if start_at + len(page) >= getattr(page, "total", len(issues)) or not page:
                    break
                start_at += len(page)
        except JiraClientError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise JiraClientError(f"Jira search failed: {type(exc).__name__}") from exc
        return issues

    def get_issue(self, issue_key: str) -> dict:
        try:
            issue = self._jira.issue(issue_key, fields=_SEARCH_FIELDS)
        except Exception as exc:  # noqa: BLE001
            raise JiraClientError(
                f"Jira issue fetch failed for {issue_key}: {type(exc).__name__}"
            ) from exc
        return self._normalise_issue(issue)

    def update_assignee(self, issue_key: str, account_id: str) -> None:
        try:
            self._jira.assign_issue(issue_key, account_id)
        except Exception as exc:  # noqa: BLE001
            raise JiraClientError(
                f"Jira reassignment failed for {issue_key}: {type(exc).__name__}"
            ) from exc

    # -- Normalisation -----------------------------------------------------

    @staticmethod
    def _normalise_issue(issue) -> dict:
        fields = issue.fields
        assignee = getattr(fields, "assignee", None)
        status = getattr(fields, "status", None)
        priority = getattr(fields, "priority", None)
        comments = []
        comment_field = getattr(fields, "comment", None)
        for comment in getattr(comment_field, "comments", []) or []:
            comments.append(
                {
                    "author": getattr(getattr(comment, "author", None), "displayName", ""),
                    "body": getattr(comment, "body", ""),
                    "created": getattr(comment, "created", ""),
                }
            )
        linked = []
        for link in getattr(fields, "issuelinks", []) or []:
            link_type = getattr(getattr(link, "type", None), "name", "") or ""
            if hasattr(link, "inwardIssue"):
                direction = getattr(getattr(link, "type", None), "inward", "") or link_type
                linked.append({"key": link.inwardIssue.key, "type": direction})
            elif hasattr(link, "outwardIssue"):
                direction = getattr(getattr(link, "type", None), "outward", "") or link_type
                linked.append({"key": link.outwardIssue.key, "type": direction})
        issue_type = getattr(fields, "issuetype", None)
        # The `parent` field carries the epic for issues in team-managed
        # projects (and the parent story for sub-tasks); only epic parents
        # are recorded.
        parent = getattr(fields, "parent", None)
        parent_epic_key = None
        if parent is not None:
            parent_type = getattr(
                getattr(getattr(parent, "fields", None), "issuetype", None), "name", ""
            )
            if (parent_type or "").strip().lower() == "epic":
                parent_epic_key = getattr(parent, "key", None)
        components = [
            name
            for component in getattr(fields, "components", []) or []
            if (name := getattr(component, "name", "") or "")
        ]
        fix_versions = [
            name
            for version in getattr(fields, "fixVersions", []) or []
            if (name := getattr(version, "name", "") or "")
        ]
        return {
            "key": issue.key,
            "summary": getattr(fields, "summary", "") or "",
            "assignee_account_id": getattr(assignee, "accountId", None)
            or getattr(assignee, "name", None),
            "assignee_display_name": getattr(assignee, "displayName", None),
            "status": getattr(status, "name", "") or "",
            "priority": getattr(priority, "name", None),
            "issue_type": getattr(issue_type, "name", None),
            "parent_epic_key": parent_epic_key,
            "components": components,
            "fix_versions": fix_versions,
            "description": getattr(fields, "description", "") or "",
            "labels": list(getattr(fields, "labels", []) or []),
            "comments": comments,
            "linked_issues": linked,
        }
