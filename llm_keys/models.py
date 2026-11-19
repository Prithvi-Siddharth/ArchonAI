"""The user_llm_settings table. Created alongside the other tables by jobs.db.init_db()."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from jobs.db import Base
from jobs.models import utcnow


class UserLLMSettings(Base):
    """One row per user: their chosen provider and their encrypted API key."""

    __tablename__ = "user_llm_settings"

    # No foreign key, like architecture_jobs.owner_id: the row is looked up by user id only.
    user_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    # Fernet token from llm_keys/crypto.py -- never the key itself.
    encrypted_key: Mapped[str] = mapped_column(Text, nullable=False)
    # Last four characters of the key, so the Bring Your Own Key page can say which key is saved.
    key_hint: Mapped[str] = mapped_column(String(8), nullable=False)
    model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)
