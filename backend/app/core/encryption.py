"""
Application-level AES-256-GCM field encryption.

Sensitive columns (tokens, emails, raw API payloads) are encrypted before
being written to Postgres and decrypted on read. The key is derived from
FIELD_ENCRYPTION_KEY in settings; rotate by re-encrypting all rows.
"""

from __future__ import annotations

import base64
import os
from typing import Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import get_settings

_NONCE_BYTES = 12  # 96-bit nonce for GCM


def _get_key() -> bytes:
    """Decode the 32-byte AES key from settings."""
    raw = get_settings().FIELD_ENCRYPTION_KEY
    return base64.urlsafe_b64decode(raw + "==")[:32]


def encrypt(plaintext: str) -> str:
    """
    Encrypt *plaintext* and return a URL-safe base64 string:
        <base64(nonce)>.<base64(ciphertext+tag)>
    """
    if not plaintext:
        return plaintext
    key = _get_key()
    nonce = os.urandom(_NONCE_BYTES)
    aesgcm = AESGCM(key)
    ct = aesgcm.encrypt(nonce, plaintext.encode(), None)
    return (
        base64.urlsafe_b64encode(nonce).decode()
        + "."
        + base64.urlsafe_b64encode(ct).decode()
    )


def decrypt(ciphertext: str) -> str:
    """
    Decrypt a value produced by :func:`encrypt`. Returns the original plaintext.
    Raises :class:`ValueError` on invalid / tampered data.
    """
    if not ciphertext or "." not in ciphertext:
        # Treat as unencrypted plaintext (migration safety)
        return ciphertext
    try:
        nonce_b64, ct_b64 = ciphertext.split(".", 1)
        nonce = base64.urlsafe_b64decode(nonce_b64 + "==")
        ct = base64.urlsafe_b64decode(ct_b64 + "==")
        key = _get_key()
        aesgcm = AESGCM(key)
        return aesgcm.decrypt(nonce, ct, None).decode()
    except Exception as exc:
        raise ValueError("Failed to decrypt field value") from exc


def encrypt_optional(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    return encrypt(value)


def decrypt_optional(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    return decrypt(value)