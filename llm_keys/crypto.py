"""Encrypt and decrypt a user's API key.

Fernet (AES-128-CBC with an HMAC) from the `cryptography` package, keyed by
HKDF over KEY_ENCRYPTION_SECRET. The user id is sealed inside the encrypted
payload and checked on the way out, so a stored key copied onto another
user's row is refused instead of being used for them.
"""

from __future__ import annotations

import base64
import json
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

_INFO = b"archonai-llm-key-v1"


def _fernet(secret: str) -> Fernet:
    key = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=_INFO).derive(secret.encode("utf-8"))
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt_key(api_key: str, user_id: str, secret: str) -> str:
    payload = json.dumps({"u": user_id, "k": api_key}, separators=(",", ":")).encode("utf-8")
    return _fernet(secret).encrypt(payload).decode("ascii")


def decrypt_key(token: str, user_id: str, secret: str) -> Optional[str]:
    """The API key, or None if the token is damaged, made with another secret, or belongs to another user."""
    try:
        payload = json.loads(_fernet(secret).decrypt(token.encode("ascii")))
    except (InvalidToken, ValueError, UnicodeError):
        return None
    if not isinstance(payload, dict) or payload.get("u") != user_id:
        return None
    key = payload.get("k")
    return key if isinstance(key, str) and key else None
