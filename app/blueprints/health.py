"""Health endpoint for container orchestration (Requirement 12.1)."""

from __future__ import annotations

from flask import Blueprint, jsonify
from sqlalchemy import text

from app.db import get_session

health_bp = Blueprint("health", __name__)


@health_bp.get("/health")
def health():
    try:
        get_session().execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001
        return jsonify({"status": "error"}), 500
    return jsonify({"status": "ok"}), 200
