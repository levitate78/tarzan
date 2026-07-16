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
    """Merge requests dashboard. The member filter takes a team member's
    Tarzan username and resolves it to their configured GitLab username
    (falling back to the Tarzan username when none is set); raw GitLab
    usernames in old URLs keep working unchanged (Requirement 6.7)."""
    raw_filter = request.args.get("member", "").strip() or None
    filter_value = raw_filter
    selected_username = None
    filter_notice = None
    if raw_filter:
        profile = profile_service().get_profile(raw_filter)
        if profile is not None:
            selected_username = profile.username
            filter_value = profile.gitlab_username or profile.username
            if not profile.gitlab_username:
                filter_notice = (
                    f"{profile.name} has no GitLab username configured, so "
                    "merge requests are matched by their Tarzan username. Set "
                    "the GitLab username on their profile for exact matching."
                )
    service = gitlab_service()
    merge_requests = service.list_merge_requests(author_or_reviewer=filter_value)
    statuses = gitlab_refresh_statuses()
    no_data = service.cache_is_empty() and not any(s.last_success for s in statuses)
    return render_template(
        "gitlab/index.html",
        merge_requests=merge_requests,
        team_members=profile_service().list_profiles(),
        selected_member=selected_username,
        filter_notice=filter_notice,
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
