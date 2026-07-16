"""Merge requests dashboard (Requirements 6 and 7)."""

from __future__ import annotations

import logging

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import login_required

from app.blueprints.common import (
    build_gitlab_client,
    enabled_gitlab_projects,
    gitlab_refresh_statuses,
    gitlab_service,
    profile_service,
)
from app.exceptions import GitLabClientError, StorageError

logger = logging.getLogger(__name__)

gitlab_bp = Blueprint("gitlab", __name__)


@gitlab_bp.get("/")
@login_required
def index():
    member = request.args.get("member", "").strip() or None
    service = gitlab_service()
    merge_requests = service.list_merge_requests(author_or_reviewer=member)
    statuses = gitlab_refresh_statuses()
    no_data = service.cache_is_empty() and not any(s.last_success for s in statuses)
    return render_template(
        "gitlab/index.html",
        merge_requests=merge_requests,
        team_members=profile_service().list_profiles(),
        selected_member=member,
        refresh_statuses=statuses,
        no_data=no_data,
    )


@gitlab_bp.post("/refresh")
@login_required
def refresh():
    """Manual refresh of every enabled GitLab project (Requirement 14): an
    explicit user action running the same fetch path as the scheduler."""
    projects = enabled_gitlab_projects()
    if not projects:
        flash("No GitLab projects are configured; add them in Settings first.", "info")
        return redirect(url_for("gitlab.index"))
    try:
        client = build_gitlab_client()
    except (GitLabClientError, StorageError):
        flash("GitLab is not reachable; the data was not refreshed.", "error")
        return redirect(url_for("gitlab.index"))
    if client is None:
        flash(
            "GitLab is not configured; set the GitLab URL and API token in Settings.",
            "error",
        )
        return redirect(url_for("gitlab.index"))

    service = gitlab_service(client=client)
    item_count = 0
    refreshed = 0
    failed: list[str] = []
    for project in projects:
        result = service.fetch_and_cache(project.gitlab_project_id)
        if result.success:
            refreshed += 1
            item_count += result.item_count
        else:
            failed.append(project.display_name or f"project {project.gitlab_project_id}")
    if refreshed:
        flash(
            f"Refreshed {refreshed} GitLab project(s): {item_count} merge "
            "request(s) fetched.",
            "success",
        )
    if failed:
        flash(
            f"Refresh failed for: {', '.join(failed)}. "
            "Existing cached data was kept.",
            "error",
        )
    return redirect(url_for("gitlab.index"))
