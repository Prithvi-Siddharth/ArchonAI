"""Issue and check the signed JWT that identifies a signed-in user.

Claims: ``sub`` (user id), ``iat``, ``exp`` and ``iss``. Only HS256 is
accepted on decode, so a token claiming another algorithm (including
"none") is rejected.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt

from auth.config import JWT_ALGORITHM, JWT_ISSUER, AuthSettings


def create_access_token(user_id: str, settings: AuthSettings, now: Optional[datetime] = None) -> str:
    assert settings.jwt_secret, "callers must check that authentication is configured"
    issued = now or datetime.now(timezone.utc)
    claims = {
        "sub": user_id,
        "iat": issued,
        "exp": issued + timedelta(minutes=settings.expire_minutes),
        "iss": JWT_ISSUER,
    }
    return jwt.encode(claims, settings.jwt_secret, algorithm=JWT_ALGORITHM)


def read_access_token(token: str, settings: AuthSettings) -> Optional[str]:
    """The user id in a valid token, or None if it is expired, tampered with or malformed."""
    if not settings.jwt_secret:
        return None
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[JWT_ALGORITHM],
            issuer=JWT_ISSUER,
            options={"require": ["sub", "iat", "exp", "iss"]},
        )
    except jwt.PyJWTError:
        return None
    subject = claims.get("sub")
    return subject if isinstance(subject, str) and subject else None
