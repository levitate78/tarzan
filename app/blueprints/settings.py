"""Settings: API credentials, refresh interval, review threshold, and
project configuration (Requirements 6.6, 8.1, 12.3)."""

from __future__ import annotations

import logging
import re

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import login_required
from sqlalchemy import select

from app.blueprints.common import config_service, credential_service
from app.constants import CREDENTIAL_GITLAB_TOKEN, CREDENTIAL_JIRA_TOKEN
from app.db import get_session
from app.exceptions import StorageError, ValidationError
from app.models import GitLabProject, JiraProject

logger = logging.getLogger(__name__)

settings_bp = Blueprint("settings", __name__)

_PROJECT_KEY_PATTERN = re.compile(r"^[A-Z][A-Z0-9]{0,19}$")
_URL_PATTERN = re.compile(r"^https?://[^\s]+$")


@settings_bp.get("/")
@login_required
def index():
    session = get_session()
    cfg = config_service()
    credentials = credential_service()
    try:
        jira_token_set = credentials.has_credential(CREDENTIAL_JIRA_TOKEN)
        gitlab_token_set = credentials.has_credential(CREDENTIAL_GITLAB_TOKEN)
    except StorageError:
        flash("The credential store is currently unavailable.", "error")
        jira_token_set = gitlab_token_set = False
    return render_template(
        "settings/index.html",
        jira_url=cfg.get_jira_url() or "",
        gitlab_url=cfg.get_gitlab_url() or "",
        jira_token_set=jira_token_set,
        gitlab_token_set=gitlab_token_set,
        refresh_interval=cfg.get_refresh_interval_minutes(),
        review_threshold=cfg.get_review_threshold_days(),
        jira_projects=session.execute(select(JiraProject)).scalars().all(),
        gitlab_projects=session.execute(select(GitLabProject)).scalars().all(),
    )


@settings_bp.post("/credentials")
@login_required
def update_credentials():
    cfg = config_service()
    credentials = credential_service()
    jira_url = request.form.get("jira_url", "").strip()
    gitlab_url = request.form.get("gitlab_url", "").strip()
    jira_token = request.form.get("jira_token", "")
    gitlab_token = request.form.get("gitlab_token", "")
    try:
        if jira_url:
            if not _URL_PATTERN.match(jira_url):
                raise ValidationError("The Jira URL must be a valid http(s) URL.", "jira_url")
            cfg.set_jira_url(jira_url)
        if gitlab_url:
            if not _URL_PATTERN.match(gitlab_url):
                raise ValidationError(
                    "The GitLab URL must be a valid http(s) URL.", "gitlab_url"
                )
            cfg.set_gitlab_url(gitlab_url)
        if jira_token:
            credentials.set_credential(CREDENTIAL_JIRA_TOKEN, jira_token)
        if gitlab_token:
            credentials.set_credential(CREDENTIAL_GITLAB_TOKEN, gitlab_token)
    except ValidationError as exc:
        flash(str(exc), "error")
    except StorageError:
        flash("The credential store is unavailable; credentials were not saved.", "error")
    else:
        flash("API settings saved.", "success")
    return redirect(url_for("settings.index"))


@settings_bp.post("/refresh-interval")
@login_required
def update_refresh_interval():
    try:
        interval = config_service().set_refresh_interval_minutes(
            request.form.get("refresh_interval", "")
        )
    except ValidationError as exc:
        flash(str(exc), "error")
    else:
        from app.scheduler import reschedule

        reschedule(current_app._get_current_object(), interval)
        flash(f"Background refresh interval set to {interval} minute(s).", "success")
    return redirect(url_for("settings.index"))


@settings_bp.post("/review-threshold")
@login_required
def update_review_threshold():
    try:
        threshold = config_service().set_review_threshold_days(
            request.form.get("review_threshold", "")
        )
    except ValidationError as exc:
        flash(str(exc), "error")
    else:
        flash(f"Review threshold set to {threshold} day(s).", "success")
    return redirect(url_for("settings.index"))


@settings_bp.post("/projects/jira")
@login_required
def add_jira_project():
    project_key = request.form.get("project_key", "").strip().upper()
    display_name = request.form.get("display_name", "").strip()
    if not _PROJECT_KEY_PATTERN.match(project_key):
        flash(
            "The Jira project key must start with an uppercase letter and "
            "contain only uppercase letters and digits (max 20 characters).",
            "error",
        )
        return redirect(url_for("settings.index"))
    session = get_session()
    existing = session.execute(
        select(JiraProject).where(JiraProject.project_key == project_key)
    ).scalar_one_or_none()
    if existing is not None:
        existing.enabled = True
        existing.display_name = display_name or existing.display_name
    else:
        session.add(JiraProject(project_key=project_key, display_name=display_name))
    session.commit()
    flash(f"Jira project {project_key} configured.", "success")
    return redirect(url_for("settings.index"))


@settings_bp.post("/projects/jira/<int:project_id>/remove")
@login_required
def remove_jira_project(project_id: int):
    session = get_session()
    project = session.get(JiraProject, project_id)
    if project is not None:
        session.delete(project)
        session.commit()
        flash(f"Jira project {project.project_key} removed.", "success")
    return redirect(url_for("settings.index"))


@settings_bp.post("/projects/gitlab")
@login_required
def add_gitlab_project():
    raw_id = request.form.get("gitlab_project_id", "").strip()
    display_name = request.form.get("display_name", "").strip()
    if not raw_id.isdigit():
        flash("The GitLab project ID must be a positive whole number.", "error")
        return redirect(url_for("settings.index"))
    gitlab_project_id = int(raw_id)
    session = get_session()
    existing = session.execute(
        select(GitLabProject).where(GitLabProject.gitlab_project_id == gitlab_project_id)
    ).scalar_one_or_none()
    if existing is not None:
        existing.enabled = True
        existing.display_name = display_name or existing.display_name
    else:
        session.add(
            GitLabProject(gitlab_project_id=gitlab_project_id, display_name=display_name)
        )
    session.commit()
    flash(f"GitLab project {gitlab_project_id} configured.", "success")
    return redirect(url_for("settings.index"))


@settings_bp.post("/projects/gitlab/<int:project_id>/remove")
@login_required
def remove_gitlab_project(project_id: int):
    session = get_session()
    project = session.get(GitLabProject, project_id)
    if project is not None:
        session.delete(project)
        session.commit()
        flash(f"GitLab project {project.gitlab_project_id} removed.", "success")
    return redirect(url_for("settings.index"))
