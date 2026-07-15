"""Login and logout (Requirements 10.4, 10.5)."""

from __future__ import annotations

import logging

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from werkzeug.security import check_password_hash

from app.auth import ManagerUser, create_server_session, destroy_server_session
from app.blueprints.common import app_config

logger = logging.getLogger(__name__)

auth_bp = Blueprint("auth", __name__)


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
            config.admin_password_hash, password
        ):
            create_server_session(username, config.session_lifetime_hours)
            login_user(ManagerUser(username))
            logger.info("Team manager logged in")
            return redirect(_safe_next_target(request.args.get("next")))
        logger.warning("Failed login attempt")
        flash("Invalid username or password.", "error")
    return render_template("auth/login.html")


@auth_bp.post("/logout")
@login_required
def logout():
    destroy_server_session()
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))
