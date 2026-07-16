"""Property tests for security invariants (design Properties 30-32)."""

from __future__ import annotations

import io
import logging
import string

from cryptography.fernet import Fernet
from hypothesis import given, settings
from hypothesis import strategies as st
from sqlalchemy import select

from app.logging_setup import SecretScrubbingFilter, TarzanJsonFormatter, register_secret
from app.models import Credential
from app.services.credential_service import CredentialService
from tests.helpers import make_memory_session


def make_service():
    session = make_memory_session()
    return session, CredentialService(session, Fernet(Fernet.generate_key()))


# Feature: team-dashboard, Property 30: Credential encryption round-trip
@given(value=st.text(min_size=1, max_size=200))
@settings(max_examples=100)
def test_credential_round_trip_and_ciphertext(value):
    session, service = make_service()
    service.set_credential("api_token", value)
    stored = session.execute(
        select(Credential).where(Credential.key == "api_token")
    ).scalar_one()
    assert bytes(stored.encrypted_value) != value.encode("utf-8")
    if len(value.encode("utf-8")) >= 4:  # short strings can appear by chance
        assert value.encode("utf-8") not in bytes(stored.encrypted_value)
    assert service.get_credential("api_token") == value


# Feature: team-dashboard, Property 31: No secrets in log output
@given(
    secret=st.text(alphabet=string.ascii_letters + string.digits, min_size=12, max_size=64)
)
@settings(max_examples=100)
def test_registered_secrets_never_appear_in_log_output(secret):
    register_secret(secret)
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(TarzanJsonFormatter())
    handler.addFilter(SecretScrubbingFilter())
    logger = logging.getLogger(f"tarzan.test.{id(stream)}")
    logger.propagate = False
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

    logger.info("token value is %s for the API", secret)
    logger.error("failure while using credential " + secret)

    output = stream.getvalue()
    assert secret not in output
    assert "[REDACTED]" in output


special_chars = st.text(
    alphabet="<>&\"'" + string.ascii_letters + " ", min_size=1, max_size=80
).filter(lambda s: any(ch in s for ch in "<>&\"'"))


# Feature: team-dashboard, Property 32: HTML output escapes special characters
# (a route-level test in tests/unit/test_routes.py confirms the same
# autoescaping is active in the real application templates)
@given(value=special_chars)
@settings(max_examples=100)
def test_rendered_html_escapes_user_input(value):
    from jinja2 import Environment

    env = Environment(autoescape=True)  # mirrors Flask's .html autoescape default
    rendered = env.from_string("<p>{{ value }}</p>").render(value=value)
    inner = rendered[len("<p>") : -len("</p>")]
    assert "<" not in inner.replace("&lt;", "")
    assert ">" not in inner.replace("&gt;", "")
    if "<" in value:
        assert "&lt;" in inner
    if ">" in value:
        assert "&gt;" in inner
    if "&" in value:
        assert "&amp;" in inner


# Feature: team-dashboard, Property 39: Password change round-trip
@given(
    new_password=st.text(min_size=8, max_size=64),
    other_password=st.text(min_size=1, max_size=64),
)
@settings(max_examples=100)
def test_password_change_round_trip(new_password, other_password):
    from unittest.mock import patch

    from werkzeug.security import check_password_hash, generate_password_hash

    from app.services.config_service import ConfigService

    service = ConfigService(make_memory_session())
    # A low-iteration hash keeps 100 examples fast; verification semantics
    # are identical to the production default.
    with patch(
        "app.services.config_service.generate_password_hash",
        lambda password: generate_password_hash(password, method="pbkdf2:sha256:1000"),
    ):
        service.set_admin_password(new_password)

    stored = service.get_admin_password_hash()
    assert stored is not None
    assert new_password not in stored  # hash never contains the plaintext
    assert check_password_hash(stored, new_password)
    if other_password != new_password:
        assert not check_password_hash(stored, other_password)
