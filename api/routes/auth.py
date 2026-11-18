"""Account endpoints: register, log in, log out, and who am I.

A successful register or login sets the session JWT in an HttpOnly,
SameSite=Strict cookie scoped to /api, so page JavaScript can never read
it. Error replies are deliberately generic: login failures never say
whether the email or the password was wrong.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.exc import SQLAlchemyError

from api.schemas import ErrorResponse, LoginRequest, RegisterRequest, UserResponse
from auth import repository
from auth.config import COOKIE_NAME, COOKIE_PATH, AuthSettings, get_auth_settings
from auth.dependencies import ACCOUNT_STORE_UNAVAILABLE, configured_auth_settings, get_current_user
from auth.models import User
from auth.passwords import burn_verification_time, hash_password, verify_password
from auth.tokens import create_access_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

_INVALID_CREDENTIALS = HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password.")
_EMAIL_TAKEN = HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists.")

_COMMON_ERRORS = {
    status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
    status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ErrorResponse},
}


def _store_unavailable(exc: SQLAlchemyError) -> HTTPException:
    # Class name only: SQLAlchemy messages can include statement parameters (email, hash).
    logger.error("Account store error (%s).", type(exc).__name__)
    return ACCOUNT_STORE_UNAVAILABLE


def _set_session_cookie(response: Response, user: User, settings: AuthSettings) -> None:
    response.set_cookie(
        COOKIE_NAME,
        create_access_token(user.id, settings),
        max_age=settings.expire_minutes * 60,
        path=COOKIE_PATH,
        httponly=True,
        samesite="strict",
        secure=settings.cookie_secure,
    )


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    response_model=UserResponse,
    responses={**_COMMON_ERRORS, status.HTTP_409_CONFLICT: {"model": ErrorResponse}},
)
def register(body: RegisterRequest, response: Response, settings: AuthSettings = Depends(configured_auth_settings)) -> UserResponse:
    """Create an account and sign in to it."""
    try:
        user = repository.create_user(body.email, hash_password(body.password))
    except repository.EmailAlreadyRegistered:
        raise _EMAIL_TAKEN from None
    except SQLAlchemyError as exc:
        raise _store_unavailable(exc) from None
    _set_session_cookie(response, user, settings)
    logger.info("Account created (user %s).", user.id)
    return UserResponse.from_user(user)


@router.post("/login", response_model=UserResponse, responses=_COMMON_ERRORS)
def login(body: LoginRequest, response: Response, settings: AuthSettings = Depends(configured_auth_settings)) -> UserResponse:
    """Sign in with email and password."""
    try:
        user = repository.get_user_by_email(body.email)
    except SQLAlchemyError as exc:
        raise _store_unavailable(exc) from None
    if user is None:
        burn_verification_time(body.password)  # same cost as a wrong password
        raise _INVALID_CREDENTIALS
    if not verify_password(body.password, user.password_hash):
        raise _INVALID_CREDENTIALS
    _set_session_cookie(response, user, settings)
    return UserResponse.from_user(user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response) -> None:
    """Sign out by deleting the session cookie. Works even when not signed in.

    The JWT itself stays valid until it expires (tokens are stateless); deleting
    the cookie removes the browser's only copy.
    """
    response.delete_cookie(
        COOKIE_NAME, path=COOKIE_PATH, httponly=True, samesite="strict", secure=get_auth_settings().cookie_secure
    )


@router.get("/me", response_model=UserResponse, responses=_COMMON_ERRORS)
def me(user: User = Depends(get_current_user)) -> UserResponse:
    """The signed-in account."""
    return UserResponse.from_user(user)
