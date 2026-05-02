"""Symmetric encryption for stored integration tokens.

The ``user_integration_credentials.token_ciphertext`` column holds
Fernet ciphertext, never plaintext — an at-rest DB leak is then
useless without the ``FERNET_KEY`` env var.

In dev the env is often unset; we derive a deterministic key from a
fixed seed so SQLite-backed tests don't crash. Production MUST set
``FERNET_KEY`` (otherwise a Railway restart invalidates every saved
token because we'd re-derive a different fallback). A startup
warning is logged when the fallback fires.
"""

from __future__ import annotations

import base64
import hashlib
import logging
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from leadgen.config import get_settings

logger = logging.getLogger(__name__)


_DEV_SEED = b"convioo-dev-fallback-key-do-not-use-in-prod"


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    raw = get_settings().fernet_key.strip()
    if not raw:
        # Deterministic dev fallback: keeps tests reproducible, but if
        # this fires in prod a restart of the container loses every
        # stored token because we'd derive the same key only as long
        # as nobody changes the seed.
        logger.warning(
            "secrets_vault: FERNET_KEY is empty — using deterministic "
            "dev fallback. DO NOT ship this to production."
        )
        material = hashlib.sha256(_DEV_SEED).digest()
        raw = base64.urlsafe_b64encode(material).decode("ascii")
    raw_bytes = raw.encode("ascii") if isinstance(raw, str) else raw
    return Fernet(raw_bytes)


def encrypt(plaintext: str) -> str:
    """Encrypt a UTF-8 token, return urlsafe-base64 ciphertext as ``str``."""
    if not isinstance(plaintext, str):
        raise TypeError("encrypt expects str input")
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt(ciphertext: str) -> str:
    """Decrypt a Fernet ciphertext string back to plaintext.

    Raises ``ValueError`` if the input is malformed or the key has
    rotated since the row was written — caller decides whether to
    surface the error or treat the credential as absent.
    """
    try:
        return _fernet().decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError) as exc:
        raise ValueError("ciphertext is invalid or key has rotated") from exc


def mask_token(plaintext: str | None) -> str:
    """``ntn_abcde...xyz`` → ``ntn…xyz`` for safe logging / UI display."""
    if not plaintext:
        return "(none)"
    cleaned = plaintext.strip()
    if len(cleaned) <= 7:
        return "*" * len(cleaned)
    return f"{cleaned[:3]}…{cleaned[-3:]}"
