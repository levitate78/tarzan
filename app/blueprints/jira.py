"""Work items dashboard, detail view, and reassignment (Requirements 4 and 5)."""

from __future__ import annotations

import logging
import re

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import login_required

from app.blueprints.common import (
    config_service,
    credential_service,
    jira_refresh_statuses,
    jira_service,
    profile_service,
)
from app.constants import CREDENTIAL_JIRA_TOKEN
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


def _build_client():
    """Build a JiraClient for an explicit user action (reassignment only —
    dashboard reads never touch the external API)."""
    cfg = config_service()
    url = cfg.get_jira_url()
    token = credential_service().get_credential(CREDENTIAL_JIRA_TOKEN)
    if not url or not token:
        return None
    from app.clients.jira_client import JiraClient

    return JiraClient(server=url, token=token)


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
        client = _build_client()
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
