"""Encryption layer: SQLCipher database key derivation and Fernet
field-level encryption (Requirements 10.1, 10.6).

The database key is derived from TARZAN_DB_KEY with PBKDF2-HMAC-SHA256 and a
fixed application salt, so it is reproducible across restarts without being
stored anywhere. Individual credential values get a second layer of
encryption with Fernet; the Fernet key itself is stored in the database
wrapped (encrypted) with a key derived from TARZAN_DB_KEY.
"""

from __future__ import annotations

import base64
import hashlib
import logging

from cryptography.fernet import Fernet
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine

from app.config import Config
from app.exceptions import StorageError
from app.logging_setup import register_secret

logger = logging.getLogger(__name__)

# Fixed application salts: distinct derivation contexts for the SQLCipher key
# and the Fernet wrapping key.
_DB_KEY_SALT = b"tarzan.sqlcipher.key.v1"
_WRAP_KEY_SALT = b"tarzan.fernet.wrap.v1"
_PBKDF2_ITERATIONS = 480_000

# Reserved credential-table key holding the wrapped Fernet key.
FERNET_KEY_CREDENTIAL = "_tarzan_fernet_key"


def derive_db_key_hex(passphrase: str) -> str:
    """Derive the 256-bit SQLCipher raw key (hex) from the passphrase."""
    derived = hashlib.pbkdf2_hmac(
        "sha256", passphrase.encode("utf-8"), _DB_KEY_SALT, _PBKDF2_ITERATIONS, dklen=32
    )
    return derived.hex()


def derive_wrapping_fernet(passphrase: str) -> Fernet:
    """Derive the Fernet used to wrap the field-level encryption key."""
    derived = hashlib.pbkdf2_hmac(
        "sha256", passphrase.encode("utf-8"), _WRAP_KEY_SALT, _PBKDF2_ITERATIONS, dklen=32
    )
    return Fernet(base64.urlsafe_b64encode(derived))


def _load_sqlcipher_dbapi():
    """Return a SQLCipher DB-API module, or None if unavailable."""
    for module_name in ("sqlcipher3.dbapi2", "pysqlcipher3.dbapi2"):
        try:
            module = __import__(module_name, fromlist=["dbapi2"])
            return module
        except ImportError:
            continue
    return None


def build_engine(config: Config) -> Engine:
    """Create the SQLAlchemy engine backed by a SQLCipher-encrypted file.

    If no SQLCipher bindings are available the application refuses to start
    unless TARZAN_ALLOW_UNENCRYPTED_DB=true (development/testing only) —
    there is no silent fallback to unencrypted storage (Requirement 10.8).
    """
    config.db_path.parent.mkdir(parents=True, exist_ok=True)
    dbapi = _load_sqlcipher_dbapi()

    if dbapi is not None:
        key_hex = derive_db_key_hex(config.db_key)
        db_path = str(config.db_path)

        def creator():
            connection = dbapi.connect(db_path)
            # PRAGMA key must be the very first operation on the connection.
            connection.execute(f"PRAGMA key = \"x'{key_hex}'\"")
            return connection

        engine = create_engine("sqlite://", creator=creator)
    elif config.allow_unencrypted_db:
        logger.warning(
            "SQLCipher bindings are not installed; running with an UNENCRYPTED "
            "database because TARZAN_ALLOW_UNENCRYPTED_DB=true. "
            "Do not use this mode in production."
        )
        engine = create_engine(f"sqlite:///{config.db_path.as_posix()}")
    else:
        logger.error(
            "SQLCipher bindings (sqlcipher3/pysqlcipher3) are not installed and "
            "TARZAN_ALLOW_UNENCRYPTED_DB is not set. Refusing to start with "
            "unencrypted storage."
        )
        raise StorageError("SQLCipher unavailable; encrypted storage required")

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def get_or_create_fernet(session, config: Config) -> Fernet:
    """Return the field-level Fernet, bootstrapping the wrapped key on first run."""
    from app.models import Credential  # local import avoids a circular dependency

    wrapper = derive_wrapping_fernet(config.db_key)
    row = session.query(Credential).filter_by(key=FERNET_KEY_CREDENTIAL).one_or_none()
    if row is None:
        fernet_key = Fernet.generate_key()
        session.add(
            Credential(key=FERNET_KEY_CREDENTIAL, encrypted_value=wrapper.encrypt(fernet_key))
        )
        session.commit()
    else:
        fernet_key = wrapper.decrypt(bytes(row.encrypted_value))
    register_secret(fernet_key.decode("ascii"))
    return Fernet(fernet_key)
