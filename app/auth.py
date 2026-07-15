"""Authentication: Flask-Login wiring with server-side session records.

A successful login creates a UserSession row; the session cookie only holds
the row's random token. Logout deletes the row, so the token is invalidated
server-side (Requirement 10.5).
"""

from __future__ import annotations

import secrets
from datetime import timedelta

from flask import current_app, render_template, session
from flask_login import LoginManager, UserMixin

from app.db import get_session
from app.models import UserSession
from app.util import utcnow

SESSION_TOKEN_KEY = "_tarzan_session_token"

login_manager = LoginManager()


class ManagerUser(UserMixin):
    """The single authenticated Team_Manager account."""

    def __init__(self, username: str):
        self.id = username
        self.username = username


@login_manager.user_loader
def load_user(user_id: str) -> ManagerUser | None:
    config = current_app.extensions["tarzan_config"]
    if user_id != config.admin_username:
        return None
    token = session.get(SESSION_TOKEN_KEY)
    if not token:
        return None
    record = (
        get_session().query(UserSession).filter_by(token=token, username=user_id).one_or_none()
    )
    if record is None:
        return None
    if record.expires_at is not None and record.expires_at < utcnow():
        db = get_session()
        db.delete(record)
        db.commit()
        return None
    return ManagerUser(user_id)


@login_manager.unauthorized_handler
def unauthorized():
    """HTTP 401 with no route/data details, pointing at the login page
    (Requirement 10.4)."""
    response = current_app.make_response(render_template("errors/401.html"))
    response.status_code = 401
    return response


def create_server_session(username: str, lifetime_hours: int) -> None:
    """Create the server-side session record and bind its token to the cookie."""
    token = secrets.token_urlsafe(32)
    db = get_session()
    db.add(
        UserSession(
            token=token,
            username=username,
            expires_at=utcnow() + timedelta(hours=lifetime_hours),
        )
    )
    db.commit()
    session[SESSION_TOKEN_KEY] = token


def destroy_server_session() -> None:
    """Delete the server-side session record (server-side invalidation)."""
    token = session.pop(SESSION_TOKEN_KEY, None)
    if token:
        db = get_session()
        record = db.query(UserSession).filter_by(token=token).one_or_none()
        if record is not None:
            db.delete(record)
            db.commit()
    session.clear()
