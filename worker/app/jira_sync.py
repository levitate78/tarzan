"""
Jira sync task.

Fetches issues for all configured projects, upserts them into the database,
resolves assignee_id by matching Jira accountId → User.jira_username, and
creates MR→Issue links for keys found in GitLab MRs.
"""

from __future__ import annotations

import sys
import os
from datetime import datetime, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

# Allow importing shared modules from the backend directory
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "backend")))

from app.config import get_settings

log = structlog.get_logger()


async def _get_session_factory():
    settings = get_settings()
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    return async_sessionmaker(engine, expire_on_commit=False)


async def sync_jira() -> None:
    # Import here to allow the path manipulation above to take effect
    from app.models import ConnectorConfig, JiraIssue, User  # type: ignore
    from app.jira import JiraConnector  # type: ignore

    SessionFactory = await _get_session_factory()

    async with SessionFactory() as db:
        configs_res = await db.execute(
            select(ConnectorConfig).where(ConnectorConfig.connector_type == "jira")
        )
        configs = configs_res.scalars().all()

        if not configs:
            log.info("jira_sync_skip", reason="no connector config")
            return

        for config in configs:
            await _sync_one_jira(db, config)


async def _sync_one_jira(db: AsyncSession, config) -> None:
    from app.jira import JiraConnector  # type: ignore
    from app.models import JiraIssue, User  # type: ignore

    connector = JiraConnector(base_url=config.base_url, token=config.token)
    project_keys = config.project_keys or []

    if not project_keys:
        log.info("jira_sync_skip", config_id=config.id, reason="no project keys")
        await connector.close()
        return

    # Delta sync: only fetch issues updated since last sync
    updated_after = config.last_synced_at

    log.info("jira_sync_start", projects=project_keys, delta=bool(updated_after))
    synced = 0
    errors = 0

    try:
        async for raw in connector.iter_issues(project_keys, updated_after=updated_after):
            try:
                normalised = connector.normalise_issue(raw, config.base_url)
                await _upsert_issue(db, normalised)
                synced += 1
            except Exception as exc:
                log.warning("jira_issue_error", key=raw.get("key"), error=str(exc))
                errors += 1

        await db.commit()

        # Update last_synced_at
        config.last_synced_at = datetime.now(timezone.utc)
        config.is_healthy = True
        await db.commit()

        log.info("jira_sync_complete", synced=synced, errors=errors)
    except Exception as exc:
        config.is_healthy = False
        await db.commit()
        log.error("jira_sync_failed", error=str(exc))
    finally:
        await connector.close()


async def _upsert_issue(db: AsyncSession, data: dict) -> None:
    from app.models import JiraIssue, User  # type: ignore

    result = await db.execute(select(JiraIssue).where(JiraIssue.key == data["key"]))
    issue = result.scalar_one_or_none()

    # Resolve assignee_id
    assignee_id = None
    if data.get("assignee_email") or data.get("assignee_display_name"):
        user_res = await db.execute(
            select(User).where(User.jira_username == data.get("assignee_display_name"))
        )
        user = user_res.scalar_one_or_none()
        if user:
            assignee_id = user.id

    now = datetime.now(timezone.utc)
    if issue:
        issue.summary = data["summary"]
        issue.description = data.get("description")
        issue.status = data["status"]
        issue.priority = data.get("priority")
        issue.issue_type = data["issue_type"]
        issue.assignee_id = assignee_id
        issue.reporter_username = data.get("reporter_username")
        issue.labels = data.get("labels", [])
        issue.jira_url = data.get("jira_url")
        issue.jira_updated_at = data.get("jira_updated_at")
        issue.synced_at = now
        issue.raw_data = data.get("raw")
    else:
        issue = JiraIssue(
            external_id=data["external_id"],
            key=data["key"],
            project_key=data["project_key"],
            summary=data["summary"],
            description=data.get("description"),
            status=data["status"],
            priority=data.get("priority"),
            issue_type=data["issue_type"],
            assignee_id=assignee_id,
            reporter_username=data.get("reporter_username"),
            labels=data.get("labels", []),
            jira_url=data.get("jira_url"),
            jira_created_at=data.get("jira_created_at"),
            jira_updated_at=data.get("jira_updated_at"),
            synced_at=now,
            raw_data=data.get("raw"),
        )
        db.add(issue)