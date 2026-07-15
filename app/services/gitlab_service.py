"""GitLab merge request caching and dashboards (Requirements 6, 7, 9)."""

from __future__ import annotations

import json
import logging
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, joinedload

from app.dtos import FetchResult, MergeRequestDTO, TicketLinkDTO
from app.exceptions import GitLabClientError
from app.models import JiraProject, MergeRequest, TicketLink, WorkItem
from app.services.cache_service import CacheService
from app.ticket_linking import extract_ticket_references
from app.util import parse_iso_datetime, utcnow

logger = logging.getLogger(__name__)


def gitlab_source_id(project_id: int) -> str:
    return f"gitlab:{project_id}"


class GitLabService:
    """Reads serve only cached data; the external API is touched exclusively
    by ``fetch_and_cache`` on the scheduler (Requirement 9.5)."""

    def __init__(
        self,
        session: Session,
        cache_service: CacheService | None = None,
        client=None,
        jira_url: str | None = None,
        review_threshold_days: int = 2,
    ):
        self._session = session
        self._cache = cache_service or CacheService(session)
        self._client = client
        self._jira_url = (jira_url or "").rstrip("/") or None
        self._threshold = timedelta(days=review_threshold_days)

    # -- Cached reads ------------------------------------------------------

    def list_merge_requests(self, author_or_reviewer: str | None = None) -> list[MergeRequestDTO]:
        merge_requests = self._session.execute(
            select(MergeRequest)
            .options(joinedload(MergeRequest.ticket_links))
            .order_by(MergeRequest.created_at.desc())
        ).unique().scalars()
        result = []
        for mr in merge_requests:
            if author_or_reviewer and not self._matches_member(mr, author_or_reviewer):
                continue
            result.append(self._to_dto(mr))
        return result

    def cache_is_empty(self) -> bool:
        return self._session.execute(select(func.count(MergeRequest.id))).scalar_one() == 0

    # -- Background refresh (Requirements 6.1, 6.2, 7.1) --------------------

    def fetch_and_cache(self, project_id: int) -> FetchResult:
        source_id = gitlab_source_id(project_id)
        if self._client is None:
            message = "GitLab credentials are not configured"
            self._cache.record_refresh(source_id, success=False, error=message)
            return FetchResult(source_id=source_id, success=False, error=message)
        try:
            merge_requests = self._client.list_merge_requests(project_id, state="opened")
        except GitLabClientError as exc:
            # Retain existing cached MRs untouched (Requirement 6.2).
            logger.error("GitLab fetch failed for project %s: %s", project_id, exc)
            self._cache.record_refresh(source_id, success=False, error=str(exc))
            return FetchResult(source_id=source_id, success=False, error=str(exc))

        try:
            self._store_merge_requests(project_id, merge_requests)
        except SQLAlchemyError as exc:
            self._session.rollback()
            logger.error("GitLab cache write failed for project %s: %s", project_id, exc)
            self._cache.record_refresh(source_id, success=False, error="cache write failed")
            return FetchResult(source_id=source_id, success=False, error="cache write failed")

        self._cache.record_refresh(source_id, success=True)
        return FetchResult(source_id=source_id, success=True, item_count=len(merge_requests))

    def _store_merge_requests(self, project_id: int, raw_mrs: list[dict]) -> None:
        project_keys = {
            key
            for key in self._session.execute(
                select(JiraProject.project_key).where(JiraProject.enabled.is_(True))
            ).scalars()
        }
        fetched_at = utcnow()
        fetched_ids = set()
        for raw in raw_mrs:
            gitlab_id = raw.get("id")
            if gitlab_id is None:
                continue
            fetched_ids.add(gitlab_id)
            mr = self._session.execute(
                select(MergeRequest).where(MergeRequest.gitlab_id == gitlab_id)
            ).scalar_one_or_none()
            if mr is None:
                mr = MergeRequest(gitlab_id=gitlab_id, project_id=project_id)
                self._session.add(mr)
            mr.project_id = project_id
            mr.title = raw.get("title") or ""
            mr.author_username = raw.get("author_username")
            mr.source_branch = raw.get("source_branch")
            mr.target_branch = raw.get("target_branch")
            mr.description = raw.get("description") or ""
            mr.review_status = raw.get("review_status") or "Awaiting Review"
            mr.reviewers_json = json.dumps(raw.get("reviewers") or [])
            mr.web_url = raw.get("web_url")
            mr.created_at = parse_iso_datetime(raw.get("created_at"))
            mr.fetched_at = fetched_at
            self._session.flush()
            self._sync_ticket_links(mr, project_keys)
        # Drop MRs that are no longer open in this project.
        stale_query = select(MergeRequest).where(MergeRequest.project_id == project_id)
        if fetched_ids:
            stale_query = stale_query.where(MergeRequest.gitlab_id.not_in(fetched_ids))
        for stale in self._session.execute(stale_query).scalars():
            self._session.delete(stale)
        self._session.commit()

    def _sync_ticket_links(self, mr: MergeRequest, project_keys: set[str]) -> None:
        """Extract ticket references from title, description, and source
        branch, and persist them as TicketLink rows (Requirement 7.1)."""
        references = set()
        for text in (mr.title, mr.description, mr.source_branch):
            references |= extract_ticket_references(text, project_keys)
        existing = {link.issue_key: link for link in mr.ticket_links}
        for reference in references:
            resolved = self._work_item_exists(reference)
            link = existing.get(reference)
            if link is None:
                mr.ticket_links.append(TicketLink(issue_key=reference, resolved=resolved))
            else:
                link.resolved = resolved
        for issue_key, link in existing.items():
            if issue_key not in references:
                self._session.delete(link)

    def _work_item_exists(self, issue_key: str) -> bool:
        return (
            self._session.execute(
                select(WorkItem.id).where(WorkItem.issue_key == issue_key)
            ).scalar_one_or_none()
            is not None
        )

    # -- Internals ---------------------------------------------------------

    @staticmethod
    def _matches_member(mr: MergeRequest, member: str) -> bool:
        """Author or reviewer match (Requirement 6.5)."""
        wanted = member.strip().lower()
        if (mr.author_username or "").lower() == wanted:
            return True
        reviewers = json.loads(mr.reviewers_json) if mr.reviewers_json else []
        return wanted in {(reviewer or "").lower() for reviewer in reviewers}

    def _to_dto(self, mr: MergeRequest) -> MergeRequestDTO:
        reviewers = tuple(json.loads(mr.reviewers_json)) if mr.reviewers_json else ()
        links = tuple(
            TicketLinkDTO(
                issue_key=link.issue_key,
                resolved=link.resolved,
                url=(
                    f"{self._jira_url}/browse/{link.issue_key}"
                    if link.resolved and self._jira_url
                    else None
                ),
            )
            for link in sorted(mr.ticket_links, key=lambda ticket: ticket.issue_key)
        )
        overdue = bool(
            mr.created_at is not None and utcnow() - mr.created_at > self._threshold
        )
        return MergeRequestDTO(
            gitlab_id=mr.gitlab_id,
            project_id=mr.project_id,
            title=mr.title,
            author_username=mr.author_username,
            target_branch=mr.target_branch,
            source_branch=mr.source_branch,
            review_status=mr.review_status,
            created_at=mr.created_at,
            web_url=mr.web_url,
            reviewers=reviewers,
            ticket_links=links,
            overdue=overdue,
        )
