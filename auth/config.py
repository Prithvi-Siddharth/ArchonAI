"""Settings for authentication, read from the environment at call time.

There is deliberately no built-in fallback secret: without a JWT_SECRET of
at least MIN_SECRET_LENGTH characters, the auth endpoints answer 503
("Authentication is not configured") instead of signing tokens with a
guessable key. Everything else in the API keeps working.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Optional

from jobs.config import _int_env

logger = logging.getLogger(__name__)

JWT_ALGORITHM = "HS256"
JWT_ISSUER = "archonai"
COOKIE_NAME = "archonai_session"
# The cookie is only sent to the API, never to the frontend's own pages.
COOKIE_PATH = "/api"
MIN_SECRET_LENGTH = 32
DEFAULT_EXPIRE_MINUTES = 8 * 60

_warned_short_secret = False


def _bool_env(name: str, default: bool) -> bool:
    """Read true/false, failing loudly on anything else (a typo must not silently mean 'off')."""
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    if raw in {"true", "1", "yes"}:
        return True
    if raw in {"false", "0", "no"}:
        return False
    raise ValueError(f"{name} must be true or false, got {raw!r}.")


@dataclass(frozen=True)
class AuthSettings:
    # None when JWT_SECRET is missing or too short: authentication is then unavailable.
    jwt_secret: Optional[str]
    expire_minutes: int
    # Send the cookie over HTTPS only. Leave false for plain-HTTP localhost.
    cookie_secure: bool


def get_auth_settings() -> AuthSettings:
    """Return the current auth settings. Never logs or returns the secret's value elsewhere."""
    global _warned_short_secret
    secret = os.getenv("JWT_SECRET", "").strip()
    if secret and len(secret) < MIN_SECRET_LENGTH:
        if not _warned_short_secret:
            logger.warning("JWT_SECRET is shorter than %d characters; authentication is disabled.", MIN_SECRET_LENGTH)
            _warned_short_secret = True
        secret = ""
    return AuthSettings(
        jwt_secret=secret or None,
        expire_minutes=_int_env("JWT_EXPIRE_MINUTES", DEFAULT_EXPIRE_MINUTES, minimum=5),
        cookie_secure=_bool_env("COOKIE_SECURE", False),
    )
