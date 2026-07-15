import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select

from app.exceptions import StorageError
from app.models import Credential
from app.services.credential_service import CredentialService
from tests.helpers import make_memory_session


@pytest.fixture()
def session():
    return make_memory_session()


@pytest.fixture()
def service(session):
    return CredentialService(session, Fernet(Fernet.generate_key()))


def test_round_trip(service):
    service.set_credential("jira_token", "super-secret-token")
    assert service.get_credential("jira_token") == "super-secret-token"


def test_stored_bytes_are_not_plaintext(session, service):
    service.set_credential("jira_token", "super-secret-token")
    row = session.execute(
        select(Credential).where(Credential.key == "jira_token")
    ).scalar_one()
    assert b"super-secret-token" not in bytes(row.encrypted_value)


def test_overwrite_updates_value(service):
    service.set_credential("jira_token", "old")
    service.set_credential("jira_token", "new")
    assert service.get_credential("jira_token") == "new"


def test_missing_credential_returns_none(service):
    assert service.get_credential("nope") is None
    assert service.has_credential("nope") is False


def test_reserved_fernet_key_is_not_readable_or_writable(service):
    with pytest.raises(StorageError):
        service.set_credential("_tarzan_fernet_key", "x")
    assert service.get_credential("_tarzan_fernet_key") is None


def test_storage_failure_raises_storage_error():
    session = make_memory_session()
    service = CredentialService(session, Fernet(Fernet.generate_key()))
    Credential.__table__.drop(session.bind)
    with pytest.raises(StorageError):
        service.set_credential("jira_token", "value")
    with pytest.raises(StorageError):
        service.get_credential("jira_token")
