"""CSRF protection and HTTPS enforcement helpers.

CSRF tokens are random per-session values stored server-side in the signed
(itsdangerous-backed) Flask session and compared in constant time. HTTPS
enforcement redirects plain HTTP before any request data is processed
(Requirement 10.7).
"""

from __future__ import annotations

import hmac
import secrets

from flask import abort, current_app, request, session

_CSRF_SESSION_KEY = "_csrf_token"

# Hosts considered "localhost context" where HTTPS is not enforced.
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


def generate_csrf_token() -> str:
    """Template global: return (creating if needed) the session CSRF token."""
    if _CSRF_SESSION_KEY not in session:
        session[_CSRF_SESSION_KEY] = secrets.token_urlsafe(32)
    return session[_CSRF_SESSION_KEY]


def validate_csrf() -> None:
    """Abort 400 when a state-changing request lacks a valid CSRF token."""
    if request.method not in ("POST", "PUT", "PATCH", "DELETE"):
        return
    expected = session.get(_CSRF_SESSION_KEY, "")
    submitted = request.form.get("csrf_token", "") or request.headers.get("X-CSRF-Token", "")
    if not expected or not hmac.compare_digest(expected, submitted):
        abort(400, description="Invalid or missing CSRF token.")


def enforce_https():
    """before_request hook: redirect plain HTTP when enforcement is enabled.

    Runs before authentication and CSRF handling so no request body or
    session data is processed on the insecure channel.
    """
    config = current_app.extensions["tarzan_config"]
    if not config.https_enforce:
        return None
    forwarded_proto = request.headers.get("X-Forwarded-Proto", "")
    scheme = forwarded_proto or request.scheme
    if scheme == "https":
        return None
    host = (request.host or "").split(":", 1)[0].lower()
    if host in _LOCAL_HOSTS:
        return None
    from flask import redirect

    return redirect(request.url.replace("http://", "https://", 1), code=301)
