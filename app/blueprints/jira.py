"""Work items dashboard, detail view, and reassignment (Requirements 4 and 5)."""

from __future__ import annotations

import logging
import re
from datetime import datetime

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import login_required

from app.blueprints.common import (
    build_jira_client,
    enabled_jira_projects,
    gitlab_service,
    jira_refresh_statuses,
    jira_service,
    profile_service,
    skills_service,
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


def _resolve_assignee_filter():
    """Resolve the assignee query parameter (a team member's Tarzan
    username) to their configured Jira account ID, falling back to display
    name when none is set; raw account IDs or display names in old URLs
    keep working unchanged (Requirement 4.9).

    Returns ``(filter_value, selected_username, notice)``."""
    raw_filter = request.args.get("assignee", "").strip() or None
    if not raw_filter:
        return None, None, None
    profile = profile_service().get_profile(raw_filter)
    if profile is None:
        return raw_filter, None, None
    notice = None
    if not profile.jira_account_id:
        notice = (
            f"{profile.name} has no Jira account ID configured, so "
            "work items are matched by display name. Set the Jira "
            "account ID on their profile for exact matching."
        )
    return profile.jira_account_id or profile.name, profile.username, notice


def _selected_filters() -> dict[str, str | None]:
    """The status/component/epic filter query parameters, normalised."""
    return {
        name: request.args.get(name, "").strip() or None
        for name in ("status", "component", "epic")
    }


@jira_bp.get("/")
@login_required
def index():
    """Work items dashboard, filterable by assignee, status, component, and
    parent epic."""
    filter_value, selected_username, filter_notice = _resolve_assignee_filter()
    filters = _selected_filters()
    service = jira_service()
    items = service.list_work_items(
        assignee=filter_value,
        status=filters["status"],
        component=filters["component"],
        epic=filters["epic"],
    )
    statuses = jira_refresh_statuses()
    no_data = service.cache_is_empty() and not any(s.last_success for s in statuses)
    return render_template(
        "jira/index.html",
        items=items,
        team_members=profile_service().list_profiles(),
        selected_assignee=selected_username,
        filters=filters,
        filter_options=service.list_filter_options(),
        filter_notice=filter_notice,
        refresh_statuses=statuses,
        no_data=no_data,
    )


@jira_bp.get("/blocked")
@login_required
def blocked():
    """Blocked work items dashboard: every blocked ticket with how long it
    has been blocked and its priority, filterable by assignee, component,
    and parent epic."""
    filter_value, selected_username, filter_notice = _resolve_assignee_filter()
    filters = _selected_filters()
    service = jira_service()
    items = service.list_work_items(
        assignee=filter_value,
        component=filters["component"],
        epic=filters["epic"],
        blocked_only=True,
    )
    # Longest-blocked first; items without a recorded start go last.
    items.sort(key=lambda item: item.blocked_since or datetime.max)
    statuses = jira_refresh_statuses()
    no_data = service.cache_is_empty() and not any(s.last_success for s in statuses)
    return render_template(
        "jira/blocked.html",
        items=items,
        team_members=profile_service().list_profiles(),
        selected_assignee=selected_username,
        filters=filters,
        filter_options=service.list_filter_options(),
        filter_notice=filter_notice,
        refresh_statuses=statuses,
        no_data=no_data,
    )


@jira_bp.get("/epics")
@login_required
def epics():
    """Epics dashboard: active epics from the configured Jira project
    filters, with progress over their child items, filterable by fix
    version."""
    fix_version = request.args.get("fix_version", "").strip() or None
    service = jira_service()
    epic_list = service.list_epics(fix_version=fix_version)
    statuses = jira_refresh_statuses()
    no_data = service.cache_is_empty() and not any(s.last_success for s in statuses)
    return render_template(
        "jira/epics.html",
        epics=epic_list,
        fix_versions=service.list_fix_versions(),
        selected_fix_version=fix_version,
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
    skills = skills_service()
    return render_template(
        "jira/detail.html",
        item=item,
        team_members=profile_service().list_profiles(),
        linked_merge_requests=gitlab_service().list_merge_requests_for_issue(issue_key),
        ticket_skills=skills.list_ticket_skills(issue_key),
        skill_catalogue=skills.list_catalogue(include_deprecated=False),
    )


@jira_bp.post("/<issue_key>/skills")
@login_required
def add_ticket_skill(issue_key: str):
    _validate_issue_key(issue_key)
    raw_skill_id = request.form.get("skill_id", "").strip()
    if not raw_skill_id.isdigit():
        flash("Choose a skill from the catalogue to link.", "error")
        return redirect(url_for("jira.detail", issue_key=issue_key))
    try:
        skill = skills_service().assign_ticket_skill(issue_key, int(raw_skill_id))
    except (NotFoundError, StorageError) as exc:
        flash(str(exc), "error")
    else:
        flash(f"Linked skill {skill.name} to {issue_key}.", "success")
    return redirect(url_for("jira.detail", issue_key=issue_key))


@jira_bp.post("/<issue_key>/skills/<int:skill_id>/remove")
@login_required
def remove_ticket_skill(issue_key: str, skill_id: int):
    _validate_issue_key(issue_key)
    try:
        skill = skills_service().remove_ticket_skill(issue_key, skill_id)
    except (NotFoundError, StorageError) as exc:
        flash(str(exc), "error")
    else:
        flash(f"Removed skill {skill.name} from {issue_key}.", "success")
    return redirect(url_for("jira.detail", issue_key=issue_key))


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
