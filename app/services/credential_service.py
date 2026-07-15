"""Encrypted credential storage (Requirements 10.1, 10.2, 10.8).

Values are Fernet-encrypted before hitting the (already SQLCipher-encrypted)
database. Plaintext values are registered with the log scrubber so they can
never appear in log output, and storage failures raise StorageError — there
is no plaintext fallback.
"""

from __future__ import annotations

import logging

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.crypto import FERNET_KEY_CREDENTIAL
from app.exceptions import StorageError
from app.logging_setup import register_secret
from app.models import Credential

logger = logging.getLogger(__name__)


class CredentialService:
    def __init__(self, session: Session, fernet: Fernet):
        self._session = session
        self._fernet = fernet

    def get_credential(self, key: str) -> str | None:
        try:
            row = self._session.query(Credential).filter_by(key=key).one_or_none()
        except SQLAlchemyError as exc:
            logger.error("Credential store read failed for key %s: %s", key, type(exc).__name__)
            raise StorageError(f"Credential store unavailable for key {key}") from exc
        if row is None or key == FERNET_KEY_CREDENTIAL:
            return None
        try:
            value = self._fernet.decrypt(bytes(row.encrypted_value)).decode("utf-8")
        except InvalidToken as exc:
            logger.error("Credential decryption failed for key %s", key)
            raise StorageError(f"Credential decryption failed for key {key}") from exc
        register_secret(value)
        return value

    def set_credential(self, key: str, value: str) -> None:
        if key == FERNET_KEY_CREDENTIAL:
            raise StorageError("Reserved credential key")
        register_secret(value)
        encrypted = self._fernet.encrypt(value.encode("utf-8"))
        try:
            row = self._session.query(Credential).filter_by(key=key).one_or_none()
            if row is None:
                self._session.add(Credential(key=key, encrypted_value=encrypted))
            else:
                row.encrypted_value = encrypted
            self._session.commit()
        except SQLAlchemyError as exc:
            self._session.rollback()
            logger.error("Credential store write failed for key %s: %s", key, type(exc).__name__)
            raise StorageError(f"Credential store write failed for key {key}") from exc

    def has_credential(self, key: str) -> bool:
        try:
            return (
                self._session.query(Credential.id).filter_by(key=key).one_or_none() is not None
            )
        except SQLAlchemyError as exc:
            raise StorageError("Credential store unavailable") from exc
