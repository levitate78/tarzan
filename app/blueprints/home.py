"""Root route: the work items dashboard is the landing page."""

from __future__ import annotations

from flask import Blueprint, redirect, url_for

home_bp = Blueprint("home", __name__)


@home_bp.get("/")
def index():
    return redirect(url_for("jira.index"))
