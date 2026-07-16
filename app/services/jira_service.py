"""Jira work item caching, dashboards, and reassignment (Requirements 4, 5, 9)."""

from __future__ import annotations

import json
import logging

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.constants import DONE_STATUSES, EPIC_ISSUE_TYPE
from app.dtos import (
    EpicDTO,
    FetchResult,
    ReassignResult,
    WorkItemDetailDTO,
    WorkItemDTO,
    WorkItemFilterOptions,
)
from app.exceptions import (
    JiraClientError,
    NotFoundError,
    ReassignError,
    ReassignTimeoutError,
)
from app.models import JiraProject, TeamMember, WorkItem
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


def _escape_jql(value: str) -> str:
    """Escape a string for embedding in a quoted JQL literal."""
    return value.replace("\\", "\\\\").replace('"', '\\"')


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
        self,
        assignee: str | None = None,
        status: str | None = None,
        component: str | None = None,
        epic: str | None = None,
        include_done: bool = False,
        blocked_only: bool = False,
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
            if status and item.status.strip().lower() != status.strip().lower():
                continue
            if component and not self._has_component(item, component):
                continue
            if epic and (item.parent_epic_key or "").upper() != epic.strip().upper():
                continue
            dto = self._to_dto(item)
            if blocked_only and not dto.is_blocked:
                continue
            result.append(dto)
        return result

    def list_filter_options(self) -> WorkItemFilterOptions:
        """Distinct statuses, components, and parent epics present in the
        cached work items, for populating dashboard filter dropdowns."""
        items = self._session.execute(select(WorkItem)).scalars().all()
        statuses: set[str] = set()
        components: set[str] = set()
        epic_summaries: dict[str, str | None] = {}
        referenced_epics: set[str] = set()
        for item in items:
            if item.status.strip():
                statuses.add(item.status.strip())
            components.update(_loads(item.components_json, []))
            if item.parent_epic_key:
                referenced_epics.add(item.parent_epic_key)
            if (item.issue_type or "").strip().lower() == EPIC_ISSUE_TYPE:
                epic_summaries[item.issue_key] = item.summary
        for key in referenced_epics:
            epic_summaries.setdefault(key, None)
        return WorkItemFilterOptions(
            statuses=tuple(sorted(statuses, key=str.lower)),
            components=tuple(sorted(components, key=str.lower)),
            epics=tuple(sorted(epic_summaries.items())),
        )

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
            issue_type=item.issue_type,
            parent_epic_key=item.parent_epic_key,
            components=tuple(_loads(item.components_json, [])),
            fix_versions=tuple(_loads(item.fix_versions_json, [])),
        )

    def list_epics(self, fix_version: str | None = None) -> list[EpicDTO]:
        """Active epics from the cached work items with progress over their
        cached child items. A fix version filter matches the epic's own fix
        versions or any child's."""
        items = self._session.execute(
            select(WorkItem).order_by(WorkItem.issue_key)
        ).scalars().all()
        children_by_epic: dict[str, list[WorkItem]] = {}
        for item in items:
            if item.parent_epic_key:
                children_by_epic.setdefault(item.parent_epic_key.upper(), []).append(item)

        wanted_version = fix_version.strip().lower() if fix_version else None
        epics = []
        for item in items:
            if (item.issue_type or "").strip().lower() != EPIC_ISSUE_TYPE:
                continue
            if item.status.strip().lower() in DONE_STATUSES:
                continue
            children = children_by_epic.get(item.issue_key.upper(), [])
            if wanted_version is not None:
                versions = {v.lower() for v in _loads(item.fix_versions_json, [])}
                for child in children:
                    versions.update(
                        v.lower() for v in _loads(child.fix_versions_json, [])
                    )
                if wanted_version not in versions:
                    continue
            epics.append(
                EpicDTO(
                    issue_key=item.issue_key,
                    summary=item.summary,
                    status=item.status,
                    priority=item.priority,
                    assignee_display_name=item.assignee_display_name,
                    fix_versions=tuple(_loads(item.fix_versions_json, [])),
                    child_total=len(children),
                    child_done=sum(
                        1
                        for child in children
                        if child.status.strip().lower() in DONE_STATUSES
                    ),
                    child_blocked=sum(
                        1
                        for child in children
                        if _is_blocked(child.status, _loads(child.linked_issues_json, []))
                    ),
                )
            )
        return epics

    def list_fix_versions(self) -> list[str]:
        """Distinct fix versions present in the cached work items."""
        versions: set[str] = set()
        for raw in self._session.execute(select(WorkItem.fix_versions_json)).scalars():
            versions.update(_loads(raw, []))
        return sorted(versions, key=str.lower)

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
            issues = self._client.search_issues(self._build_jql(project_key))
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

    def _build_jql(self, project_key: str) -> str:
        """Base project query, restricted to the project's configured
        components when any are set (Settings)."""
        jql = f'project = "{project_key}"'
        components = self._project_components(project_key)
        if components:
            quoted = ", ".join(f'"{_escape_jql(name)}"' for name in components)
            jql += f" AND component in ({quoted})"
        return jql + " ORDER BY updated DESC"

    def _project_components(self, project_key: str) -> list[str]:
        project = self._session.execute(
            select(JiraProject).where(JiraProject.project_key == project_key)
        ).scalar_one_or_none()
        if project is None:
            return []
        return _loads(project.components_json, [])

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
            item.issue_type = raw.get("issue_type")
            item.parent_epic_key = raw.get("parent_epic_key")
            item.components_json = json.dumps(raw.get("components") or [])
            item.fix_versions_json = json.dumps(raw.get("fix_versions") or [])
            item.description_json = json.dumps(raw.get("description") or "")
            item.labels_json = json.dumps(raw.get("labels") or [])
            item.linked_issues_json = json.dumps(raw.get("linked_issues") or [])
            item.comments_json = json.dumps(raw.get("comments") or [])
            # Track when the item first appeared blocked so the blocked
            # dashboard can show how long it has been stuck.
            if _is_blocked(item.status, raw.get("linked_issues") or []):
                if item.blocked_since is None:
                    item.blocked_since = fetched_at
            else:
                item.blocked_since = None
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

    @staticmethod
    def _has_component(item: WorkItem, component: str) -> bool:
        wanted = component.strip().lower()
        return wanted in {c.lower() for c in _loads(item.components_json, [])}

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
            issue_type=item.issue_type,
            parent_epic_key=item.parent_epic_key,
            components=tuple(_loads(item.components_json, [])),
            fix_versions=tuple(_loads(item.fix_versions_json, [])),
            blocked_since=item.blocked_since,
        )
