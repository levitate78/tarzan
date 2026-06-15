"""Smoke tests verifying module wiring: import paths, re-exports, RBAC.

These don't require a database — they catch the kind of import-path errors
(``app.api.deps``, ``app.core.security``, ``app.connectors.*``) that would
otherwise only surface at application startup.
"""

from __future__ import annotations


def test_app_imports_and_exposes_expected_routes():
    from app.main import app

    paths = {route.path for route in app.routes}

    assert "/health" in paths
    assert "/api/v1/auth/login" in paths
    assert "/api/v1/auth/me" in paths
    assert "/api/v1/dashboard/team" in paths
    assert "/api/v1/dashboard/member/{user_id}" in paths
    assert "/api/v1/issues" in paths
    assert "/api/v1/issues/{issue_id}/reassign" in paths
    assert "/api/v1/merge-requests" in paths
    assert "/api/v1/skills/matrix" in paths
    assert "/api/v1/config/connectors" in paths
    assert "/api/v1/config/review-threshold" in paths


def test_api_deps_reexports():
    from app.api.deps import CurrentUser, DB, get_current_user, require_role, write_audit_log

    assert callable(get_current_user)
    assert callable(write_audit_log)
    assert CurrentUser is not None
    assert DB is not None


def test_core_security_roundtrip():
    from app.core.security import create_access_token, decode_access_token, hash_password, verify_password

    hashed = hash_password("a-very-secure-password-123")
    assert hashed != "a-very-secure-password-123"
    assert verify_password("a-very-secure-password-123", hashed)
    assert not verify_password("wrong-password", hashed)

    token = create_access_token(subject="user-id-123", role="member")
    payload = decode_access_token(token)
    assert payload["sub"] == "user-id-123"
    assert payload["role"] == "member"


def test_connectors_package_reexports():
    from app.connectors import GitLabConnector, JiraConnector
    from app.connectors.gitlab import GitLabConnector as DirectGitLab
    from app.connectors.jira import JiraConnector as DirectJira
    from app.gitlab import GitLabConnector as OriginalGitLab
    from app.jira import JiraConnector as OriginalJira

    assert GitLabConnector is DirectGitLab is OriginalGitLab
    assert JiraConnector is DirectJira is OriginalJira


def test_rbac_role_weights():
    from app.core.rbac import Role, has_role

    assert has_role("admin", Role.viewer)
    assert has_role("lead", Role.member)
    assert not has_role("viewer", Role.lead)
    assert not has_role("not-a-real-role", Role.viewer)


def test_field_encryption_roundtrip():
    from app.core.encryption import decrypt, encrypt

    ciphertext = encrypt("super-secret-token")
    assert ciphertext != "super-secret-token"
    assert decrypt(ciphertext) == "super-secret-token"
