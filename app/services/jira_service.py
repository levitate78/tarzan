"""Jira work item caching, dashboards, and reassignment (Requirements 4, 5, 9)."""

from __future__ import annotations

import json
import logging

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.constants import DONE_STATUSES
from app.dtos import FetchResult, ReassignResult, WorkItemDetailDTO, WorkItemDTO
from app.exceptions import (
    JiraClientError,
    NotFoundError,
    ReassignError,
    ReassignTimeoutError,
)
from app.models import TeamMember, WorkItem
from app.services.cache_service import CacheService
from app.util import utcnow

logger = logging.getLogger(__name__)


def jira_source_id(project_key: str) -> str:
    return f"jira:{project_key}"


def _loads(raw: str | None, default):
    if not raw:
        return default
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return default


def _is_blocked(status: str, linked_issues: list[dict]) -> bool:
    """Blocked status or any blocking link (Requirement 4.4)."""
    if status.strip().lower() == "blocked":
        return True
    return any("block" in (link.get("type") or "").lower() for link in linked_issues)


class JiraService:
    """Reads serve only cached data; the external API is touched exclusively
    by ``fetch_and_cache`` (scheduler) and ``reassign_work_item``
    (explicit user action) — never during a dashboard page render
    (Requirement 9.5)."""

    def __init__(
        self,
        session: Session,
        cache_service: CacheService | None = None,
        client=None,
        in_review_statuses: set[str] | None = None,
    ):
        self._session = session
        self._cache = cache_service or CacheService(session)
        self._client = client
        self._in_review = {s.lower() for s in (in_review_statuses or {"in review"})}

    # -- Cached reads ------------------------------------------------------

    def list_work_items(
        self, assignee: str | None = None, include_done: bool = False
    ) -> list[WorkItemDTO]:
        items = self._session.execute(
            select(WorkItem).order_by(WorkItem.issue_key)
        ).scalars()
        result = []
        for item in items:
            if not include_done and item.status.strip().lower() in DONE_STATUSES:
                continue
            if assignee and not self._matches_assignee(item, assignee):
                continue
            result.append(self._to_dto(item))
        return result

    def get_work_item(self, issue_key: str) -> WorkItemDetailDTO | None:
        item = self._get_item(issue_key)
        if item is None:
            return None
        linked = _loads(item.linked_issues_json, [])
        return WorkItemDetailDTO(
            issue_key=item.issue_key,
            summary=item.summary,
            assignee_account_id=item.assignee_account_id,
            assignee_display_name=item.assignee_display_name,
            status=item.status,
            priority=item.priority,
            description=_loads(item.description_json, ""),
            comments=tuple(_loads(item.comments_json, [])),
            labels=tuple(_loads(item.labels_json, [])),
            linked_issues=tuple(linked),
            is_blocked=_is_blocked(item.status, linked),
            is_in_review=item.status.strip().lower() in self._in_review,
        )

    def cache_is_empty(self) -> bool:
        return self._session.execute(select(func.count(WorkItem.id))).scalar_one() == 0

    # -- Reassignment (Requirement 5) ---------------------------------------

    def reassign_work_item(self, issue_key: str, assignee_account_id: str) -> ReassignResult:
        if self._client is None:
            raise ReassignError("Jira is not configured; set credentials in Settings.")
        item = self._get_item(issue_key)
        if item is None:
            raise NotFoundError(f"Work item {issue_key} is not in the cache.")
        member = self._session.execute(
            select(TeamMember).where(
                (TeamMember.jira_account_id == assignee_account_id)
                | (TeamMember.username == assignee_account_id)
            )
        ).scalar_one_or_none()
        if member is None:
            raise ReassignError("The selected assignee is not a configured team member.")
        account_id = member.jira_account_id or member.username

        try:
            self._client.update_assignee(issue_key, account_id)
        except JiraClientError as exc:
            if "timeout" in str(exc).lower() or "timed out" in str(exc).lower():
                raise ReassignTimeoutError(
                    f"Jira did not respond in time; {issue_key} was not reassigned."
                ) from exc
            raise ReassignError(
                f"Jira rejected the reassignment of {issue_key}; the work item is unchanged."
            ) from exc

        # Success: update the cached item immediately (Requirement 5.2).
        item.assignee_account_id = account_id
        item.assignee_display_name = member.name
        self._session.commit()
        return ReassignResult(
            issue_key=issue_key,
            new_assignee_account_id=account_id,
            new_assignee_display_name=member.name,
        )

    # -- Background refresh (Requirements 4.1, 4.2, 8.3, 8.4) ---------------

    def fetch_and_cache(self, project_key: str) -> FetchResult:
        source_id = jira_source_id(project_key)
        if self._client is None:
            message = "Jira credentials are not configured"
            self._cache.record_refresh(source_id, success=False, error=message)
            return FetchResult(source_id=source_id, success=False, error=message)
        try:
            issues = self._client.search_issues(
                f'project = "{project_key}" ORDER BY updated DESC'
            )
        except JiraClientError as exc:
            # Retain existing cached items untouched (Requirement 4.2).
            logger.error("Jira fetch failed for project %s: %s", project_key, exc)
            self._cache.record_refresh(source_id, success=False, error=str(exc))
            return FetchResult(source_id=source_id, success=False, error=str(exc))

        try:
            self._store_issues(project_key, issues)
        except SQLAlchemyError as exc:
            self._session.rollback()
            logger.error("Jira cache write failed for project %s: %s", project_key, exc)
            self._cache.record_refresh(source_id, success=False, error="cache write failed")
            return FetchResult(source_id=source_id, success=False, error="cache write failed")

        self._cache.record_refresh(source_id, success=True)
        return FetchResult(source_id=source_id, success=True, item_count=len(issues))

    def _store_issues(self, project_key: str, issues: list[dict]) -> None:
        fetched_at = utcnow()
        fetched_keys = set()
        for raw in issues:
            key = raw.get("key")
            if not key:
                continue
            fetched_keys.add(key)
            item = self._get_item(key) or WorkItem(issue_key=key, project_key=project_key)
            item.project_key = project_key
            item.summary = raw.get("summary") or ""
            item.assignee_account_id = raw.get("assignee_account_id")
            item.assignee_display_name = raw.get("assignee_display_name")
            item.status = raw.get("status") or ""
            item.priority = raw.get("priority")
            item.description_json = json.dumps(raw.get("description") or "")
            item.labels_json = json.dumps(raw.get("labels") or [])
            item.linked_issues_json = json.dumps(raw.get("linked_issues") or [])
            item.comments_json = json.dumps(raw.get("comments") or [])
            item.fetched_at = fetched_at
            self._session.add(item)
        # Remove items that no longer exist in the project's result set.
        stale_query = select(WorkItem).where(WorkItem.project_key == project_key)
        if fetched_keys:
            stale_query = stale_query.where(WorkItem.issue_key.not_in(fetched_keys))
        stale_items = self._session.execute(stale_query).scalars()
        for stale in stale_items:
            self._session.delete(stale)
        self._session.commit()

    # -- Internals ---------------------------------------------------------

    def _get_item(self, issue_key: str) -> WorkItem | None:
        return self._session.execute(
            select(WorkItem).where(WorkItem.issue_key == issue_key)
        ).scalar_one_or_none()

    @staticmethod
    def _matches_assignee(item: WorkItem, assignee: str) -> bool:
        wanted = assignee.strip().lower()
        return wanted in {
            (item.assignee_account_id or "").lower(),
            (item.assignee_display_name or "").lower(),
        }

    def _to_dto(self, item: WorkItem) -> WorkItemDTO:
        linked = _loads(item.linked_issues_json, [])
        return WorkItemDTO(
            issue_key=item.issue_key,
            summary=item.summary,
            assignee_account_id=item.assignee_account_id,
            assignee_display_name=item.assignee_display_name,
            status=item.status,
            priority=item.priority,
            is_blocked=_is_blocked(item.status, linked),
            is_in_review=item.status.strip().lower() in self._in_review,
            fetched_at=item.fetched_at,
        )
