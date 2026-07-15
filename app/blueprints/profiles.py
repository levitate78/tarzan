"""Team member profile routes (Requirement 1)."""

from __future__ import annotations

import logging
import re

from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from flask_login import login_required

from app.blueprints.common import profile_service, skills_service
from app.constants import MAX_AVATAR_BYTES
from app.exceptions import ConflictError, NotFoundError, StorageError, ValidationError
from app.services.profile_service import CreateProfileInput, UpdateProfileInput

logger = logging.getLogger(__name__)

profiles_bp = Blueprint("profiles", __name__)

_USERNAME_PATTERN = re.compile(r"^[\w.@+-]{1,120}$")


def _validate_username_param(username: str) -> str:
    if not _USERNAME_PATTERN.match(username or ""):
        abort(404)
    return username


@profiles_bp.get("/")
@login_required
def index():
    return render_template("profiles/index.html", profiles=profile_service().list_profiles())


@profiles_bp.get("/<username>")
@login_required
def detail(username: str):
    _validate_username_param(username)
    profile = profile_service().get_profile(username)
    if profile is None:
        abort(404)
    try:
        matrix = skills_service().list_matrix(username)
    except NotFoundError:
        matrix = []
    return render_template("profiles/detail.html", profile=profile, matrix=matrix)


@profiles_bp.route("/new", methods=["GET", "POST"])
@login_required
def new():
    if request.method == "POST":
        data = CreateProfileInput(
            name=request.form.get("name", ""),
            username=request.form.get("username", ""),
            jira_account_id=request.form.get("jira_account_id", ""),
            gitlab_username=request.form.get("gitlab_username", ""),
        )
        try:
            profile = profile_service().create_profile(data)
        except (ValidationError, ConflictError, StorageError) as exc:
            flash(str(exc), "error")
        else:
            _maybe_save_avatar(profile.username)
            flash(f"Profile for {profile.name} created.", "success")
            return redirect(url_for("profiles.detail", username=profile.username))
    return render_template("profiles/edit.html", profile=None, mode="new")


@profiles_bp.route("/<username>/edit", methods=["GET", "POST"])
@login_required
def edit(username: str):
    _validate_username_param(username)
    service = profile_service()
    profile = service.get_profile(username)
    if profile is None:
        abort(404)
    if request.method == "POST":
        data = UpdateProfileInput(
            name=request.form.get("name", ""),
            username=request.form.get("username", ""),
            jira_account_id=request.form.get("jira_account_id", ""),
            gitlab_username=request.form.get("gitlab_username", ""),
        )
        try:
            updated = service.update_profile(username, data)
        except (ValidationError, ConflictError, NotFoundError, StorageError) as exc:
            flash(str(exc), "error")
        else:
            _maybe_save_avatar(updated.username)
            flash("Profile updated.", "success")
            return redirect(url_for("profiles.detail", username=updated.username))
    return render_template("profiles/edit.html", profile=profile, mode="edit")


@profiles_bp.post("/<username>/avatar")
@login_required
def upload_avatar(username: str):
    _validate_username_param(username)
    if _maybe_save_avatar(username, required=True):
        flash("Avatar updated.", "success")
    return redirect(url_for("profiles.detail", username=username))


@profiles_bp.get("/<username>/avatar.img")
@login_required
def serve_avatar(username: str):
    """Stream the avatar after validating the stored path is inside the
    avatar directory (path traversal defence)."""
    _validate_username_param(username)
    path = profile_service().resolve_avatar_file(username)
    if path is None:
        abort(404)
    return send_file(path, max_age=300)


def _maybe_save_avatar(username: str, required: bool = False) -> bool:
    """Save an uploaded avatar file if present; flash validation errors."""
    upload = request.files.get("avatar")
    if upload is None or not upload.filename:
        if required:
            flash("Choose an avatar file to upload.", "error")
        return False
    file_bytes = upload.read(MAX_AVATAR_BYTES + 1)
    try:
        profile_service().save_avatar(username, file_bytes, upload.mimetype or "")
    except (ValidationError, NotFoundError, StorageError) as exc:
        flash(str(exc), "error")
        return False
    return True
