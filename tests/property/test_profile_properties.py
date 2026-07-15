"""Property tests for the profile service (design Properties 1-4)."""

from __future__ import annotations

import string

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from app.constants import ALLOWED_AVATAR_MIME_TYPES, MAX_AVATAR_BYTES
from app.exceptions import ConflictError, ValidationError
from app.services.profile_service import (
    CreateProfileInput,
    ProfileService,
    UpdateProfileInput,
)
from tests.helpers import make_memory_session

nonblank_text = st.text(min_size=1, max_size=60).filter(lambda s: s.strip())
whitespace_text = st.text(alphabet=" \t\n\r\x0b\x0c", max_size=20)
ascii_username = st.text(
    alphabet=string.ascii_letters + string.digits, min_size=1, max_size=30
)


def make_service(tmp_path_factory=None):
    import tempfile
    from pathlib import Path

    avatars = Path(tempfile.mkdtemp()) / "avatars"
    return ProfileService(make_memory_session(), avatars)


# Feature: team-dashboard, Property 1: Profile persistence round-trip
@given(name=nonblank_text, username=nonblank_text, new_name=nonblank_text)
@settings(max_examples=100)
def test_profile_round_trip(name, username, new_name):
    service = make_service()
    service.create_profile(CreateProfileInput(name=name, username=username))
    fetched = service.get_profile(username)
    assert fetched is not None
    assert fetched.name == name.strip()
    assert fetched.username == username.strip()

    service.update_profile(username, UpdateProfileInput(name=new_name, username=username))
    updated = service.get_profile(username)
    assert updated.name == new_name.strip()


# Feature: team-dashboard, Property 2: Whitespace-only profile fields are rejected
@given(bad_value=whitespace_text, good_value=nonblank_text, bad_field=st.sampled_from(["name", "username"]))
@settings(max_examples=100)
def test_whitespace_only_fields_rejected(bad_value, good_value, bad_field):
    service = make_service()
    data = {"name": good_value, "username": good_value}
    data[bad_field] = bad_value
    with pytest.raises(ValidationError):
        service.create_profile(CreateProfileInput(**data))
    assert service.list_profiles() == []


# Feature: team-dashboard, Property 3: Username uniqueness invariant
@given(username=ascii_username, name=nonblank_text, variant=st.sampled_from(["upper", "lower", "swapcase", "padded"]))
@settings(max_examples=100)
def test_username_uniqueness(username, name, variant):
    service = make_service()
    service.create_profile(CreateProfileInput(name=name, username=username))
    duplicate = {
        "upper": username.upper(),
        "lower": username.lower(),
        "swapcase": username.swapcase(),
        "padded": f"  {username}\t",
    }[variant]
    with pytest.raises(ConflictError):
        service.create_profile(CreateProfileInput(name=name, username=duplicate))
    assert len(service.list_profiles()) == 1


# Feature: team-dashboard, Property 4: Avatar file validation
@given(
    size=st.integers(min_value=0, max_value=MAX_AVATAR_BYTES + 1024),
    mime_type=st.sampled_from(
        sorted(ALLOWED_AVATAR_MIME_TYPES) + ["image/svg+xml", "text/html", "application/pdf", ""]
    ),
)
@settings(max_examples=100, deadline=None)  # multi-MB file writes exceed the default deadline
def test_avatar_validation(size, mime_type):
    service = make_service()
    service.create_profile(CreateProfileInput(name="Alice", username="alice"))
    file_bytes = b"x" * size
    should_accept = mime_type in ALLOWED_AVATAR_MIME_TYPES and size <= MAX_AVATAR_BYTES
    if should_accept:
        path = service.save_avatar("alice", file_bytes, mime_type)
        assert service.get_profile("alice").avatar_path == path
    else:
        with pytest.raises(ValidationError):
            service.save_avatar("alice", file_bytes, mime_type)
        assert service.get_profile("alice").avatar_path is None
