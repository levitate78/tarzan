"""Change-password flow (Requirement 15)."""

from __future__ import annotations

from app import create_app
from tests.conftest import ADMIN_PASSWORD, csrf_for, login, make_test_config

NEW_PASSWORD = "brand-new-secret-42"


def change_password(client, current, new, confirm=None):
    token = csrf_for(client, "/auth/change-password")
    return client.post(
        "/auth/change-password",
        data={
            "current_password": current,
            "new_password": new,
            "confirm_password": confirm if confirm is not None else new,
            "csrf_token": token,
        },
        follow_redirects=True,
    )


def logout(client):
    token = csrf_for(client, "/profiles/")
    return client.post("/auth/logout", data={"csrf_token": token})


def test_change_password_page_requires_authentication(client):
    assert client.get("/auth/change-password").status_code == 401


def test_wrong_current_password_rejected_and_password_unchanged(logged_in_client):
    body = change_password(logged_in_client, "not-the-password", NEW_PASSWORD).get_data(
        as_text=True
    )
    assert "The current password is incorrect." in body
    logout(logged_in_client)
    assert login(logged_in_client).status_code == 302  # old password still valid


def test_short_new_password_rejected(logged_in_client):
    body = change_password(logged_in_client, ADMIN_PASSWORD, "short").get_data(as_text=True)
    assert "at least 8 characters" in body
    logout(logged_in_client)
    assert login(logged_in_client).status_code == 302


def test_mismatched_confirmation_rejected(logged_in_client):
    body = change_password(
        logged_in_client, ADMIN_PASSWORD, NEW_PASSWORD, confirm="different-thing"
    ).get_data(as_text=True)
    assert "do not match" in body
    logout(logged_in_client)
    assert login(logged_in_client).status_code == 302


def test_change_password_applies_immediately(logged_in_client):
    body = change_password(logged_in_client, ADMIN_PASSWORD, NEW_PASSWORD).get_data(
        as_text=True
    )
    assert "Password changed." in body
    logout(logged_in_client)

    old = login(logged_in_client)
    assert "Invalid username or password" in old.get_data(as_text=True)
    assert login(logged_in_client, password=NEW_PASSWORD).status_code == 302


def test_changed_password_survives_restart(app, tmp_path):
    client = app.test_client()
    assert login(client).status_code == 302
    change_password(client, ADMIN_PASSWORD, NEW_PASSWORD)

    # A second app over the same data directory simulates a restart; the
    # stored hash must win over the TARZAN_ADMIN_PASSWORD-derived hash.
    restarted = create_app(make_test_config(tmp_path))
    fresh_client = restarted.test_client()
    assert "Invalid username or password" in login(fresh_client).get_data(as_text=True)
    assert login(fresh_client, password=NEW_PASSWORD).status_code == 302


def test_other_sessions_invalidated_on_change(app):
    changer = app.test_client()
    bystander = app.test_client()
    assert login(changer).status_code == 302
    assert login(bystander).status_code == 302
    assert bystander.get("/profiles/").status_code == 200

    change_password(changer, ADMIN_PASSWORD, NEW_PASSWORD)

    # The session that made the change stays valid; all others are revoked.
    assert changer.get("/profiles/").status_code == 200
    assert bystander.get("/profiles/").status_code == 401


def test_new_password_never_appears_in_logs(logged_in_client, capsys):
    change_password(logged_in_client, ADMIN_PASSWORD, NEW_PASSWORD)
    captured = capsys.readouterr()
    assert NEW_PASSWORD not in captured.out
    assert NEW_PASSWORD not in captured.err
