"""Password hashing with the standard library's scrypt (no extra dependency).

Stored format: ``scrypt$<n>$<r>$<p>$<salt b64>$<hash b64>``. The parameters
travel with each hash, so they can be raised later without breaking
existing accounts. Plain passwords are never stored or logged.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

# One of OWASP's equivalent scrypt minimums (N=2^15, r=8, p=3): 32 MiB of memory per hash
# instead of the 128 MiB that N=2^17, p=1 would need, at the same overall cost.
SCRYPT_N = 2**15
SCRYPT_R = 8
SCRYPT_P = 3
_DKLEN = 32
_SALT_BYTES = 16
_MAXMEM = 64 * 1024 * 1024


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _derive(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p, maxmem=_MAXMEM, dklen=_DKLEN)


def hash_password(password: str) -> str:
    """Hash a password with a fresh random salt."""
    salt = secrets.token_bytes(_SALT_BYTES)
    digest = _derive(password, salt, SCRYPT_N, SCRYPT_R, SCRYPT_P)
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    """True if `password` matches `stored`. A malformed stored hash never matches."""
    try:
        scheme, n, r, p, salt_b64, digest_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        salt = base64.b64decode(salt_b64, validate=True)
        expected = base64.b64decode(digest_b64, validate=True)
        actual = _derive(password, salt, int(n), int(r), int(p))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


# Checked when a login names an unknown email, so that case costs the same
# time as a wrong password and response timing doesn't reveal which emails exist.
_DUMMY_HASH = hash_password(secrets.token_urlsafe(16))


def burn_verification_time(password: str) -> None:
    verify_password(password, _DUMMY_HASH)
