"""FastAPI dependencies for routes that need a signed-in user.

Usage::

    @router.get("/something")
    def handler(user: User = Depends(get_current_user)): ...

The user is identified only by the signed JWT in the HttpOnly session
cookie; nothing the client sends in a body, query or header is trusted
as identity.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyCookie
from sqlalchemy.exc import SQLAlchemyError

from auth import repository
from auth.config import COOKIE_NAME, AuthSettings, get_auth_settings
from auth.models import User
from auth.tokens import read_access_token

logger = logging.getLogger(__name__)

# Documents the cookie in /docs; auto_error=False so the 401 below has our own message.
session_cookie = APIKeyCookie(name=COOKIE_NAME, auto_error=False, description="Session JWT set by /api/v1/auth/login.")

NOT_CONFIGURED = HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Authentication is not configured.")
NOT_AUTHENTICATED = HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in, or the session has expired.")
ACCOUNT_STORE_UNAVAILABLE = HTTPException(
    status.HTTP_503_SERVICE_UNAVAILABLE, "Account store is unavailable. Please retry later."
)


def configured_auth_settings() -> AuthSettings:
    """The auth settings, or 503 when no usable JWT_SECRET is set."""
    settings = get_auth_settings()
    if not settings.jwt_secret:
        raise NOT_CONFIGURED
    return settings


def get_current_user(
    token: Optional[str] = Depends(session_cookie),
    settings: AuthSettings = Depends(configured_auth_settings),
) -> User:
    """The signed-in user, or 401. A valid token for a deleted account is also 401."""
    user_id = read_access_token(token, settings) if token else None
    if user_id is None:
        raise NOT_AUTHENTICATED
    try:
        user = repository.get_user(user_id)
    except SQLAlchemyError as exc:
        # Class name only: SQLAlchemy messages can include statement parameters.
        logger.error("Account lookup failed (%s).", type(exc).__name__)
        raise ACCOUNT_STORE_UNAVAILABLE from None
    if user is None:
        raise NOT_AUTHENTICATED
    return user
