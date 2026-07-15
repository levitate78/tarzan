import pytest

from app.constants import MAX_AVATAR_BYTES
from app.exceptions import ConflictError, NotFoundError, ValidationError
from app.services.profile_service import (
    CreateProfileInput,
    ProfileService,
    UpdateProfileInput,
)
from tests.helpers import make_memory_session


@pytest.fixture()
def service(tmp_path):
    return ProfileService(make_memory_session(), tmp_path / "avatars")


def test_create_and_get_profile(service):
    created = service.create_profile(CreateProfileInput(name="Alice Smith", username="alice"))
    fetched = service.get_profile("alice")
    assert fetched == created
    assert fetched.name == "Alice Smith"


def test_update_profile_reflects_new_values(service):
    service.create_profile(CreateProfileInput(name="Alice", username="alice"))
    service.update_profile("alice", UpdateProfileInput(name="Alice B", username="aliceb"))
    assert service.get_profile("alice") is None
    updated = service.get_profile("aliceb")
    assert updated.name == "Alice B"


@pytest.mark.parametrize("field", ["name", "username"])
@pytest.mark.parametrize("value", ["", "   ", "\t\n"])
def test_empty_required_fields_rejected(service, field, value):
    data = {"name": "Alice", "username": "alice"}
    data[field] = value
    with pytest.raises(ValidationError) as excinfo:
        service.create_profile(CreateProfileInput(**data))
    assert excinfo.value.field == field
    assert service.list_profiles() == []


def test_duplicate_username_rejected_case_insensitive(service):
    service.create_profile(CreateProfileInput(name="Alice", username="alice"))
    with pytest.raises(ConflictError):
        service.create_profile(CreateProfileInput(name="Other", username="  ALICE "))
    assert len(service.list_profiles()) == 1


def test_update_missing_profile_raises_not_found(service):
    with pytest.raises(NotFoundError):
        service.update_profile("ghost", UpdateProfileInput(name="G", username="ghost"))


def test_avatar_accepts_valid_upload(service, tmp_path):
    service.create_profile(CreateProfileInput(name="Alice", username="alice"))
    path = service.save_avatar("alice", b"\x89PNG fake bytes", "image/png")
    assert path.endswith(".png")
    assert service.get_profile("alice").avatar_path == path


def test_avatar_rejects_bad_mime_type(service):
    service.create_profile(CreateProfileInput(name="Alice", username="alice"))
    with pytest.raises(ValidationError):
        service.save_avatar("alice", b"data", "image/svg+xml")
    assert service.get_profile("alice").avatar_path is None


def test_avatar_rejects_oversize_file(service):
    service.create_profile(CreateProfileInput(name="Alice", username="alice"))
    with pytest.raises(ValidationError):
        service.save_avatar("alice", b"x" * (MAX_AVATAR_BYTES + 1), "image/png")
    assert service.get_profile("alice").avatar_path is None


def test_avatar_at_size_limit_accepted(service):
    service.create_profile(CreateProfileInput(name="Alice", username="alice"))
    path = service.save_avatar("alice", b"x" * MAX_AVATAR_BYTES, "image/webp")
    assert path.endswith(".webp")
