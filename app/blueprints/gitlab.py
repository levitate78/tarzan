"""Merge requests dashboard (Requirements 6 and 7)."""

from __future__ import annotations

import logging

from flask import Blueprint, render_template, request
from flask_login import login_required

from app.blueprints.common import (
    gitlab_refresh_statuses,
    gitlab_service,
    profile_service,
)

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
