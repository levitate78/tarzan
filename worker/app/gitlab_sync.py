"""
GitLab sync task.

Fetches Merge Requests for configured GitLab projects, upserts them into the
database, links MRs to Jira issues by extracted keys, and computes breach
flags based on the ReviewThreshold setting.
"""

from __future__ import annotations

import sys
import os
from datetime import datetime, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

# Ensure backend app package is importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend")))

from app.config import get_settings

log = structlog.get_logger()


async def _get_session_factory():
    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    return async_sessionmaker(engine, expire_on_commit=False)


async def sync_gitlab() -> None:
    from app.models import ConnectorConfig, GitLabMR, JiraIssue, MRIssueLink, ReviewThreshold  # type: ignore
    from app.gitlab import GitLabConnector  # type: ignore

    SessionFactory = await _get_session_factory()

    async with SessionFactory() as db:
        configs_res = await db.execute(
            select(ConnectorConfig).where(ConnectorConfig.connector_type == "gitlab")
        )
        configs = configs_res.scalars().all()

        if not configs:
            log.info("gitlab_sync_skip", reason="no connector config")
            return

        # Load global threshold
        thresh_res = await db.execute(select(ReviewThreshold).limit(1))
        threshold = thresh_res.scalar_one_or_none()
        threshold_hours = threshold.threshold_hours if threshold else get_settings().DEFAULT_REVIEW_THRESHOLD_HOURS

        for config in configs:
            await _sync_one_gitlab(db, config, threshold_hours)


async def _sync_one_gitlab(db: AsyncSession, config, threshold_hours: float) -> None:
    from app.gitlab import GitLabConnector  # type: ignore
    from app.models import GitLabMR, JiraIssue, MRIssueLink  # type: ignore

    connector = GitLabConnector(base_url=config.base_url, token=config.token)
    project_ids = config.project_ids or []

    if not project_ids:
        log.info("gitlab_sync_skip", config_id=config.id, reason="no project ids")
        await connector.close()
        return

    log.info("gitlab_sync_start", projects=project_ids)
    synced = 0
    errors = 0

    try:
        for pid in project_ids:
            async for raw in connector.iter_mrs(pid):
                try:
                    project = await connector.get_project(pid)
                    normalised = connector.normalise_mr(raw, project.get("name", ""), threshold_hours)
                    await _upsert_mr(db, normalised)
                    synced += 1
                except Exception as exc:
                    log.warning("gitlab_mr_error", iid=raw.get("iid"), error=str(exc))
                    errors += 1

        await db.commit()
        config.last_synced_at = datetime.now(timezone.utc)
        config.is_healthy = True
        await db.commit()
        log.info("gitlab_sync_complete", synced=synced, errors=errors)
    except Exception as exc:
        config.is_healthy = False
        await db.commit()
        log.error("gitlab_sync_failed", error=str(exc))
    finally:
        await connector.close()


async def _upsert_mr(db: AsyncSession, data: dict) -> None:
    from app.models import GitLabMR, JiraIssue, MRIssueLink  # type: ignore
    from sqlalchemy import select

    result = await db.execute(select(GitLabMR).where(GitLabMR.external_id == data["external_id"], GitLabMR.project_id == data["project_id"]))
    mr = result.scalar_one_or_none()

    now = datetime.now(timezone.utc)
    if mr:
        mr.title = data["title"]
        mr.description = data.get("description")
        mr.state = data.get("state", "opened")
        mr.author_username = data.get("author_username")
        mr.assignee_usernames = data.get("assignee_usernames", [])
        mr.reviewer_usernames = data.get("reviewer_usernames", [])
        mr.source_branch = data.get("source_branch")
        mr.target_branch = data.get("target_branch")
        mr.web_url = data.get("web_url")
        mr.jira_issue_keys = data.get("jira_issue_keys", [])
        mr.review_age_hours = data.get("review_age_hours", 0.0)
        mr.breach_threshold_hours = data.get("breach_threshold_hours", 24.0)
        mr.breached = data.get("breached", False)
        mr.mr_updated_at = data.get("mr_updated_at")
        mr.mr_merged_at = data.get("mr_merged_at")
        mr.synced_at = now
    else:
        mr = GitLabMR(
            external_id=data["external_id"],
            project_id=data["project_id"],
            project_name=data.get("project_name", ""),
            title=data["title"],
            description=data.get("description"),
            state=data.get("state", "opened"),
            author_username=data.get("author_username"),
            assignee_usernames=data.get("assignee_usernames", []),
            reviewer_usernames=data.get("reviewer_usernames", []),
            source_branch=data.get("source_branch"),
            target_branch=data.get("target_branch"),
            web_url=data.get("web_url"),
            jira_issue_keys=data.get("jira_issue_keys", []),
            review_age_hours=data.get("review_age_hours", 0.0),
            breach_threshold_hours=data.get("breach_threshold_hours", 24.0),
            breached=data.get("breached", False),
            mr_created_at=data.get("mr_created_at"),
            mr_updated_at=data.get("mr_updated_at"),
            mr_merged_at=data.get("mr_merged_at"),
            synced_at=now,
        )
        db.add(mr)

    # Link to Jira issues
    keys = data.get("jira_issue_keys") or []
    for key in keys:
        res = await db.execute(select(JiraIssue).where(JiraIssue.key == key))
        ji = res.scalar_one_or_none()
        if ji:
            # ensure link exists
            link_res = await db.execute(select(MRIssueLink).where(MRIssueLink.mr_id == mr.id, MRIssueLink.issue_id == ji.id))
            link = link_res.scalar_one_or_none()
            if not link:
                link = MRIssueLink(mr_id=mr.id, issue_id=ji.id)
                db.add(link)
