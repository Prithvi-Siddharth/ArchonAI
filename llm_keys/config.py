"""Settings for storing users' API keys, read from the environment at call time.

Like JWT_SECRET, there is deliberately no built-in fallback: without a
KEY_ENCRYPTION_SECRET of at least MIN_SECRET_LENGTH characters, saving a key
answers 503 instead of encrypting with a guessable secret. Jobs keep using
the server's own key.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

MIN_SECRET_LENGTH = 32

_warned_short_secret = False


def get_encryption_secret() -> Optional[str]:
    """The usable KEY_ENCRYPTION_SECRET, or None. The value is never logged."""
    global _warned_short_secret
    secret = os.getenv("KEY_ENCRYPTION_SECRET", "").strip()
    if secret and len(secret) < MIN_SECRET_LENGTH:
        if not _warned_short_secret:
            logger.warning("KEY_ENCRYPTION_SECRET is shorter than %d characters; saving API keys is disabled.", MIN_SECRET_LENGTH)
            _warned_short_secret = True
        return None
    return secret or None
