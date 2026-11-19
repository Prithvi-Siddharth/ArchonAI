"""Turn a job owner's saved settings into credentials for one run."""

from __future__ import annotations

from typing import Optional

from agents.llm import LLMCredentials
from llm_keys import repository
from llm_keys.config import get_encryption_secret
from llm_keys.crypto import decrypt_key
from llm_keys.providers import PROVIDERS


class StoredKeyUnusableError(RuntimeError):
    """The owner saved a key, but it can't be used (secret missing or changed, damaged row).

    The job must fail instead of quietly falling back to the server's key: that
    would spend the server owner's quota on a user who chose their own provider.
    """


def credentials_for(owner_id: Optional[str]) -> Optional[LLMCredentials]:
    """The owner's own credentials, or None when they have none (the server's key is used)."""
    if not owner_id:
        return None
    row = repository.get_settings(owner_id)
    if row is None:
        return None
    secret = get_encryption_secret()
    api_key = decrypt_key(row.encrypted_key, owner_id, secret) if secret else None
    if api_key is None or row.provider not in PROVIDERS:
        raise StoredKeyUnusableError()
    return LLMCredentials(provider=row.provider, api_key=api_key, model=row.model)
