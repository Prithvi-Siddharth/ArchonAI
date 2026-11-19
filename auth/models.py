"""The users table. Created alongside the job tables by jobs.db.init_db()."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from jobs.db import Base
from jobs.models import utcnow


def new_user_id() -> str:
    return str(uuid.uuid4())


class User(Base):
    """One account. The email is stored normalised (trimmed, lowercase)."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_user_id)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True, nullable=False)
    # scrypt hash from auth/passwords.py -- never the password itself.
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    # Optional name shown instead of the email; the email stays the sign-in.
    display_name: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    # Carried in every session token. A password change adds 1, so every older token stops working.
    token_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
