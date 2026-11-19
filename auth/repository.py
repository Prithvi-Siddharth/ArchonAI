"""Read and create users. The API only touches the users table through here."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from auth.models import User
from jobs.db import session_scope


class EmailAlreadyRegistered(Exception):
    """Raised when an account with the email already exists."""


def create_user(email: str, password_hash: str) -> User:
    """Store a new user. `email` must already be normalised (see api/schemas.py)."""
    try:
        with session_scope() as session:
            user = User(email=email, password_hash=password_hash)
            session.add(user)
            session.flush()
            return user
    except IntegrityError:
        # The unique index on email: also covers two registrations racing each other.
        raise EmailAlreadyRegistered() from None


def get_user_by_email(email: str) -> Optional[User]:
    with session_scope() as session:
        return session.execute(select(User).where(User.email == email)).scalar_one_or_none()


def get_user(user_id: str) -> Optional[User]:
    with session_scope() as session:
        return session.get(User, user_id)


def set_display_name(user_id: str, display_name: Optional[str]) -> Optional[User]:
    """Set (or, with None, clear) the display name. None if the user no longer exists."""
    with session_scope() as session:
        user = session.get(User, user_id)
        if user is None:
            return None
        user.display_name = display_name
        session.flush()
        return user


def change_password(user_id: str, password_hash: str) -> Optional[User]:
    """Store a new password hash and add 1 to the token version, which ends every older session.

    One UPDATE statement, so two simultaneous changes can't both keep the same version.
    """
    with session_scope() as session:
        user = session.get(User, user_id)
        if user is None:
            return None
        session.execute(
            update(User).where(User.id == user_id).values(password_hash=password_hash, token_version=User.token_version + 1)
        )
        session.refresh(user)
        return user
