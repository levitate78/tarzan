"""Shared helpers for blueprint route handlers: per-request service
construction and dashboard refresh status assembly."""

from __future__ import annotations

from flask import current_app
from sqlalchemy import select

from app.constants import CREDENTIAL_GITLAB_TOKEN, CREDENTIAL_JIRA_TOKEN
from app.db import get_session
from app.dtos import RefreshStatusDTO
from app.models import GitLabProject, JiraProject
from app.services.cache_service import CacheService
from app.services.config_service import ConfigService
from app.services.credential_service import CredentialService
from app.services.gitlab_service import GitLabService, gitlab_source_id
from app.services.jira_service import JiraService, jira_source_id
from app.services.profile_service import ProfileService
from app.services.skills_service import SkillsService


def app_config():
    return current_app.extensions["tarzan_config"]


def profile_service() -> ProfileService:
    return ProfileService(get_session(), app_config().avatars_dir)


def skills_service() -> SkillsService:
    return SkillsService(get_session())


def config_service() -> ConfigService:
    return ConfigService(get_session())


def cache_service() -> CacheService:
    return CacheService(get_session())


def credential_service() -> CredentialService:
    return CredentialService(get_session(), current_app.extensions["tarzan_fernet"])


def jira_service(client=None) -> JiraService:
    return JiraService(
        get_session(),
        cache_service=cache_service(),
        client=client,
        in_review_statuses=config_service().get_in_review_statuses(),
    )


def gitlab_service(client=None) -> GitLabService:
    cfg = config_service()
    return GitLabService(
        get_session(),
        cache_service=cache_service(),
        client=client,
        jira_url=cfg.get_jira_url(),
        review_threshold_days=cfg.get_review_threshold_days(),
    )


def build_jira_client():
    """A JiraClient for an explicit user action (reassignment, manual
    refresh) — dashboard reads never touch the external API. Returns None
    when the URL or token is not configured."""
    url = config_service().get_jira_url()
    token = credential_service().get_credential(CREDENTIAL_JIRA_TOKEN)
    if not url or not token:
        return None
    from app.clients.jira_client import JiraClient

    return JiraClient(server=url, token=token)


def build_gitlab_client():
    """A GitLabClient for an explicit user action (manual refresh). Returns
    None when the URL or token is not configured."""
    url = config_service().get_gitlab_url()
    token = credential_service().get_credential(CREDENTIAL_GITLAB_TOKEN)
    if not url or not token:
        return None
    from app.clients.gitlab_client import GitLabClient

    return GitLabClient(url=url, token=token)


def enabled_jira_projects() -> list[JiraProject]:
    return list(
        get_session()
        .execute(select(JiraProject).where(JiraProject.enabled.is_(True)))
        .scalars()
    )


def enabled_gitlab_projects() -> list[GitLabProject]:
    return list(
        get_session()
        .execute(select(GitLabProject).where(GitLabProject.enabled.is_(True)))
        .scalars()
    )


def jira_refresh_statuses() -> list[RefreshStatusDTO]:
    interval = config_service().get_refresh_interval_minutes()
    cache = cache_service()
    return [
        cache.get_refresh_status(
            jira_source_id(project.project_key),
            project.display_name or project.project_key,
            interval,
        )
        for project in enabled_jira_projects()
    ]


def gitlab_refresh_statuses() -> list[RefreshStatusDTO]:
    interval = config_service().get_refresh_interval_minutes()
    cache = cache_service()
    return [
        cache.get_refresh_status(
            gitlab_source_id(project.gitlab_project_id),
            project.display_name or f"GitLab project {project.gitlab_project_id}",
            interval,
        )
        for project in enabled_gitlab_projects()
    ]
