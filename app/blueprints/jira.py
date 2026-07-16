"""Work items dashboard, detail view, and reassignment (Requirements 4 and 5)."""

from __future__ import annotations

import logging
import re

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import login_required

from app.blueprints.common import (
    build_jira_client,
    enabled_jira_projects,
    jira_refresh_statuses,
    jira_service,
    profile_service,
)
from app.exceptions import (
    JiraClientError,
    NotFoundError,
    ReassignError,
    ReassignTimeoutError,
    StorageError,
    ValidationError,
)

logger = logging.getLogger(__name__)

jira_bp = Blueprint("jira", __name__)

_ISSUE_KEY_PATTERN = re.compile(r"^[A-Z][A-Z0-9]*-[0-9]{1,6}$")


def _validate_issue_key(issue_key: str) -> str:
    if not _ISSUE_KEY_PATTERN.match(issue_key or ""):
        abort(404)
    return issue_key


@jira_bp.get("/")
@login_required
def index():
    assignee = request.args.get("assignee", "").strip() or None
    service = jira_service()
    items = service.list_work_items(assignee=assignee)
    statuses = jira_refresh_statuses()
    no_data = service.cache_is_empty() and not any(s.last_success for s in statuses)
    return render_template(
        "jira/index.html",
        items=items,
        team_members=profile_service().list_profiles(),
        selected_assignee=assignee,
        refresh_statuses=statuses,
        no_data=no_data,
    )


@jira_bp.post("/refresh")
@login_required
def refresh():
    """Manual refresh of every enabled Jira project (Requirement 14): an
    explicit user action running the same fetch path as the scheduler."""
    projects = enabled_jira_projects()
    if not projects:
        flash("No Jira projects are configured; add them in Settings first.", "info")
        return redirect(url_for("jira.index"))
    try:
        client = build_jira_client()
    except (JiraClientError, StorageError):
        flash("Jira is not reachable; the data was not refreshed.", "error")
        return redirect(url_for("jira.index"))
    if client is None:
        flash(
            "Jira is not configured; set the Jira URL and API token in Settings.",
            "error",
        )
        return redirect(url_for("jira.index"))

    service = jira_service(client=client)
    item_count = 0
    refreshed = 0
    failed: list[str] = []
    for project in projects:
        result = service.fetch_and_cache(project.project_key)
        if result.success:
            refreshed += 1
            item_count += result.item_count
        else:
            failed.append(project.display_name or project.project_key)
    if refreshed:
        flash(
            f"Refreshed {refreshed} Jira project(s): {item_count} work item(s) fetched.",
            "success",
        )
    if failed:
        flash(
            f"Refresh failed for: {', '.join(failed)}. "
            "Existing cached data was kept.",
            "error",
        )
    return redirect(url_for("jira.index"))


@jira_bp.get("/<issue_key>")
@login_required
def detail(issue_key: str):
    _validate_issue_key(issue_key)
    try:
        item = jira_service().get_work_item(issue_key)
    except StorageError:
        # Requirement 4.8: report the failure and keep the dashboard usable.
        flash("The work item detail view failed to load. Please try again.", "error")
        return redirect(url_for("jira.index"))
    if item is None:
        flash("That work item is not in the cache.", "error")
        return redirect(url_for("jira.index"))
    return render_template(
        "jira/detail.html", item=item, team_members=profile_service().list_profiles()
    )


@jira_bp.post("/<issue_key>/reassign")
@login_required
def reassign(issue_key: str):
    _validate_issue_key(issue_key)
    assignee = request.form.get("assignee", "").strip()
    if not assignee:
        flash("Choose a team member to assign the work item to.", "error")
        return redirect(url_for("jira.detail", issue_key=issue_key))
    try:
        client = build_jira_client()
    except (JiraClientError, StorageError):
        flash("Jira is not reachable; the work item was not reassigned.", "error")
        return redirect(url_for("jira.detail", issue_key=issue_key))
    try:
        result = jira_service(client=client).reassign_work_item(issue_key, assignee)
    except ReassignTimeoutError:
        flash(
            "Jira did not respond within the timeout; the work item was not "
            "reassigned.",
            "error",
        )
    except (ReassignError, NotFoundError, ValidationError) as exc:
        flash(str(exc), "error")
    else:
        flash(
            f"{result.issue_key} reassigned to "
            f"{result.new_assignee_display_name or result.new_assignee_account_id}.",
            "success",
        )
    return redirect(url_for("jira.detail", issue_key=issue_key))
