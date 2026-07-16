"""Tarzan application factory."""

from __future__ import annotations

import logging

from flask import Flask, render_template, request
from sqlalchemy.orm import sessionmaker

from app.config import Config
from app.crypto import build_engine, get_or_create_fernet
from app.db import close_session
from app.logging_setup import setup_logging
from app.models import Base
from app.security import enforce_https, generate_csrf_token, validate_csrf

logger = logging.getLogger(__name__)


def create_app(config: Config | None = None) -> Flask:
    if config is None:
        config = Config.from_env()
    setup_logging(getattr(logging, config.log_level.upper(), logging.INFO))

    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=config.secret_key,
        TESTING=config.testing,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=config.https_enforce,
        MAX_CONTENT_LENGTH=6 * 1024 * 1024,  # avatar limit plus form overhead
    )
    app.extensions["tarzan_config"] = config

    # -- Persistence -----------------------------------------------------
    config.data_dir.mkdir(parents=True, exist_ok=True)
    engine = build_engine(config)
    Base.metadata.create_all(engine)
    app.extensions["tarzan_engine"] = engine
    app.extensions["tarzan_session_factory"] = sessionmaker(bind=engine)

    bootstrap_session = app.extensions["tarzan_session_factory"]()
    try:
        app.extensions["tarzan_fernet"] = get_or_create_fernet(bootstrap_session, config)
        from app.services.cache_service import CacheService

        CacheService(bootstrap_session).prune_old_entries()
    finally:
        bootstrap_session.close()

    # -- Request lifecycle -------------------------------------------------
    # Order matters: HTTPS enforcement runs before anything touches request
    # data (Requirement 10.7), then CSRF validation for state-changing requests.
    app.before_request(enforce_https)
    app.before_request(validate_csrf)
    app.teardown_appcontext(close_session)

    # -- Authentication ----------------------------------------------------
    from app.auth import login_manager

    login_manager.init_app(app)

    # -- Blueprints ----------------------------------------------------------
    from app.blueprints.auth import auth_bp
    from app.blueprints.gitlab import gitlab_bp
    from app.blueprints.health import health_bp
    from app.blueprints.home import home_bp
    from app.blueprints.jira import jira_bp
    from app.blueprints.profiles import profiles_bp
    from app.blueprints.settings import settings_bp
    from app.blueprints.skills import skills_bp

    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(profiles_bp, url_prefix="/profiles")
    app.register_blueprint(skills_bp, url_prefix="/skills")
    app.register_blueprint(jira_bp, url_prefix="/jira")
    app.register_blueprint(gitlab_bp, url_prefix="/gitlab")
    app.register_blueprint(settings_bp, url_prefix="/settings")
    app.register_blueprint(health_bp)
    app.register_blueprint(home_bp)

    # -- Templates -----------------------------------------------------------
    app.jinja_env.globals["csrf_token"] = generate_csrf_token

    @app.template_filter("minute")
    def format_to_minute(value):
        """Render a datetime accurate to the nearest minute (Requirement 8.6)."""
        if value is None:
            return "never"
        return value.strftime("%Y-%m-%d %H:%M")

    @app.template_filter("duration")
    def format_duration(value):
        """Human-readable elapsed time since a naive UTC datetime
        (e.g. '3 days', '2 hours', 'less than an hour')."""
        from app.util import utcnow

        if value is None:
            return "unknown"
        elapsed = utcnow() - value
        if elapsed.days >= 1:
            return f"{elapsed.days} day{'s' if elapsed.days != 1 else ''}"
        hours = elapsed.seconds // 3600
        if hours >= 1:
            return f"{hours} hour{'s' if hours != 1 else ''}"
        return "less than an hour"

    # -- Error handlers (Requirement 10.4, design: HTTP error pages) --------
    @app.errorhandler(400)
    def bad_request(error):
        return render_template("errors/400.html", description=error.description), 400

    @app.errorhandler(401)
    def unauthorized(_error):
        return render_template("errors/401.html"), 401

    @app.errorhandler(403)
    def forbidden(_error):
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def not_found(_error):
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def server_error(_error):
        logger.error("Unhandled server error on %s", request.path)
        return render_template("errors/500.html"), 500

    # -- Background updater ----------------------------------------------
    if config.scheduler_enabled and not config.testing:
        from app.scheduler import start_scheduler

        with app.app_context():
            start_scheduler(app)

    return app
