"""Background_Updater: periodic refresh of Jira and GitLab data
(Requirement 8).

Runs on an APScheduler BackgroundScheduler so page requests keep serving
cached data while a refresh is in flight. All exceptions are caught and
recorded — the scheduler thread never crashes.
"""

from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask
from sqlalchemy import select

from app.constants import CREDENTIAL_GITLAB_TOKEN, CREDENTIAL_JIRA_TOKEN
from app.exceptions import StorageError, TarzanError
from app.models import GitLabProject, JiraProject
from app.services.cache_service import CacheService
from app.services.config_service import ConfigService
from app.services.credential_service import CredentialService
from app.services.gitlab_service import GitLabService
from app.services.jira_service import JiraService

logger = logging.getLogger(__name__)

REFRESH_JOB_ID = "tarzan_refresh_all"


def _build_jira_client(config_service: ConfigService, credentials: CredentialService):
    url = config_service.get_jira_url()
    token = credentials.get_credential(CREDENTIAL_JIRA_TOKEN)
    if not url or not token:
        return None
    from app.clients.jira_client import JiraClient

    return JiraClient(server=url, token=token)


def _build_gitlab_client(config_service: ConfigService, credentials: CredentialService):
    url = config_service.get_gitlab_url()
    token = credentials.get_credential(CREDENTIAL_GITLAB_TOKEN)
    if not url or not token:
        return None
    from app.clients.gitlab_client import GitLabClient

    return GitLabClient(url=url, token=token)


def refresh_all(app: Flask) -> None:
    """One refresh cycle over every enabled Jira and GitLab project."""
    with app.app_context():
        session = app.extensions["tarzan_session_factory"]()
        try:
            cache = CacheService(session)
            config_service = ConfigService(session)
            credentials = CredentialService(session, app.extensions["tarzan_fernet"])

            try:
                jira_client = _build_jira_client(config_service, credentials)
            except (TarzanError, StorageError) as exc:
                logger.error("Could not build Jira client: %s", exc)
                jira_client = None
            jira_service = JiraService(
                session,
                cache_service=cache,
                client=jira_client,
                in_review_statuses=config_service.get_in_review_statuses(),
            )
            for project_key in session.execute(
                select(JiraProject.project_key).where(JiraProject.enabled.is_(True))
            ).scalars():
                try:
                    result = jira_service.fetch_and_cache(project_key)
                    if not result.success:
                        logger.error(
                            "Jira refresh failed for source %s: %s",
                            result.source_id,
                            result.error,
                        )
                except Exception as exc:  # noqa: BLE001 - never crash the scheduler
                    logger.exception("Unexpected error refreshing Jira project %s", project_key)
                    cache.record_refresh(
                        f"jira:{project_key}", success=False, error=type(exc).__name__
                    )

            try:
                gitlab_client = _build_gitlab_client(config_service, credentials)
            except (TarzanError, StorageError) as exc:
                logger.error("Could not build GitLab client: %s", exc)
                gitlab_client = None
            gitlab_service = GitLabService(
                session,
                cache_service=cache,
                client=gitlab_client,
                jira_url=config_service.get_jira_url(),
                review_threshold_days=config_service.get_review_threshold_days(),
            )
            for project_id in session.execute(
                select(GitLabProject.gitlab_project_id).where(GitLabProject.enabled.is_(True))
            ).scalars():
                try:
                    result = gitlab_service.fetch_and_cache(project_id)
                    if not result.success:
                        logger.error(
                            "GitLab refresh failed for source %s: %s",
                            result.source_id,
                            result.error,
                        )
                except Exception as exc:  # noqa: BLE001
                    logger.exception("Unexpected error refreshing GitLab project %s", project_id)
                    cache.record_refresh(
                        f"gitlab:{project_id}", success=False, error=type(exc).__name__
                    )
        except Exception:  # noqa: BLE001 - never crash the scheduler thread
            logger.exception("Background refresh cycle failed")
        finally:
            session.close()


def start_scheduler(app: Flask) -> BackgroundScheduler:
    """Create and start the background scheduler with the configured interval."""
    session = app.extensions["tarzan_session_factory"]()
    try:
        interval_minutes = ConfigService(session).get_refresh_interval_minutes()
    finally:
        session.close()

    scheduler = BackgroundScheduler(daemon=True)
    scheduler.add_job(
        refresh_all,
        trigger="interval",
        minutes=interval_minutes,
        args=[app],
        id=REFRESH_JOB_ID,
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    logger.info("Background updater started with a %s minute interval", interval_minutes)
    app.extensions["tarzan_scheduler"] = scheduler
    return scheduler


def reschedule(app: Flask, interval_minutes: int) -> None:
    """Apply a new refresh interval to a running scheduler."""
    scheduler = app.extensions.get("tarzan_scheduler")
    if scheduler is not None:
        scheduler.reschedule_job(REFRESH_JOB_ID, trigger="interval", minutes=interval_minutes)
        logger.info("Background updater rescheduled to every %s minutes", interval_minutes)
