"""Read and create users. The API only touches the users table through here."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import select
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
