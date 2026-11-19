"""Read and write a user's LLM settings row. Routes and the job runner go through here."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import delete

from jobs.db import session_scope
from jobs.models import utcnow
from llm_keys.models import UserLLMSettings


def get_settings(user_id: str) -> Optional[UserLLMSettings]:
    with session_scope() as session:
        return session.get(UserLLMSettings, user_id)


def save_settings(user_id: str, *, provider: str, encrypted_key: str, key_hint: str, model: Optional[str]) -> UserLLMSettings:
    """Create the row, or replace everything in it."""
    with session_scope() as session:
        row = session.get(UserLLMSettings, user_id)
        if row is None:
            row = UserLLMSettings(user_id=user_id, provider=provider, encrypted_key=encrypted_key, key_hint=key_hint, model=model)
            session.add(row)
        else:
            row.provider = provider
            row.encrypted_key = encrypted_key
            row.key_hint = key_hint
            row.model = model
            row.updated_at = utcnow()
        session.flush()
        return row


def update_model(user_id: str, model: Optional[str]) -> Optional[UserLLMSettings]:
    """Change only the model of an existing row; None if there is no row."""
    with session_scope() as session:
        row = session.get(UserLLMSettings, user_id)
        if row is None:
            return None
        row.model = model
        row.updated_at = utcnow()
        session.flush()
        return row


def delete_settings(user_id: str) -> bool:
    with session_scope() as session:
        return session.execute(delete(UserLLMSettings).where(UserLLMSettings.user_id == user_id)).rowcount > 0
