"""Example architecture prompts served by the API.

The prompts themselves live in data/example_prompts.json so they can be
added or reworded without touching code -- the same content-as-data pattern
used for the AWS service knowledge base (tools/aws_service_search.py).
"""

from __future__ import annotations

import json
from pathlib import Path

_DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "example_prompts.json"
_PROMPTS_CACHE: list[dict[str, str]] | None = None


def load_example_prompts() -> list[dict[str, str]]:
    """Return the example prompts as a list of {"label", "prompt"} dicts, in display order."""
    global _PROMPTS_CACHE
    if _PROMPTS_CACHE is None:
        with _DATA_PATH.open("r", encoding="utf-8") as f:
            _PROMPTS_CACHE = json.load(f)
    return _PROMPTS_CACHE
