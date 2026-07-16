"""Login, logout, and password management (Requirements 10.4, 10.5, 15)."""

from __future__ import annotations

import logging

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user
from werkzeug.security import check_password_hash

from app.auth import SESSION_TOKEN_KEY, ManagerUser, create_server_session, destroy_server_session
from app.blueprints.common import app_config, config_service
from app.constants import MIN_PASSWORD_LENGTH
from app.db import get_session
from app.exceptions import StorageError, ValidationError
from app.logging_setup import register_secret
from app.models import UserSession

logger = logging.getLogger(__name__)

auth_bp = Blueprint("auth", __name__)


def _active_password_hash() -> str:
    """The UI-set hash when one exists, otherwise the hash derived from
    TARZAN_ADMIN_PASSWORD (Requirement 15.3)."""
    return config_service().get_admin_password_hash() or app_config().admin_password_hash


def _safe_next_target(target: str | None) -> str:
    """Only allow relative redirect targets (open-redirect defence)."""
    if target and target.startswith("/") and not target.startswith("//"):
        return target
    return url_for("home.index")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("home.index"))
    if request.method == "POST":
        config = app_config()
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if username == config.admin_username and check_password_hash(
            _active_password_hash(), password
        ):
            create_server_session(username, config.session_lifetime_hours)
            login_user(ManagerUser(username))
            logger.info("Team manager logged in")
            return redirect(_safe_next_target(request.args.get("next")))
        logger.warning("Failed login attempt")
        flash("Invalid username or password.", "error")
    return render_template("auth/login.html")


@auth_bp.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    """Change the manager password from the UI (Requirement 15). Error
    messages never echo any submitted value (Requirement 10.3)."""
    if request.method == "POST":
        current = request.form.get("current_password", "")
        new = request.form.get("new_password", "")
        confirmation = request.form.get("confirm_password", "")
        try:
            if not check_password_hash(_active_password_hash(), current):
                raise ValidationError("The current password is incorrect.")
            if len(new) < MIN_PASSWORD_LENGTH:
                raise ValidationError(
                    "The new password must be at least "
                    f"{MIN_PASSWORD_LENGTH} characters long."
                )
            if new != confirmation:
                raise ValidationError("The new password and its confirmation do not match.")
            register_secret(new)  # never allow the new password into log output
            config_service().set_admin_password(new)
            _invalidate_other_sessions()
        except ValidationError as exc:
            flash(str(exc), "error")
        except StorageError:
            flash("The password could not be saved. Please try again.", "error")
        else:
            logger.info("Team manager password changed")
            flash(
                "Password changed. Any other active sessions have been logged out.",
                "success",
            )
            return redirect(url_for("settings.index"))
    return render_template("auth/change_password.html")


def _invalidate_other_sessions() -> None:
    """Server-side invalidation of every session except the one making the
    change (Requirement 15.5)."""
    current_token = session.get(SESSION_TOKEN_KEY)
    db = get_session()
    for record in db.query(UserSession).filter_by(username=current_user.username):
        if record.token != current_token:
            db.delete(record)
    db.commit()


@auth_bp.post("/logout")
@login_required
def logout():
    destroy_server_session()
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))
