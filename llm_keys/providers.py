"""The providers a user can bring a key for (the ones agents/llm.py can build)."""

from __future__ import annotations

from dataclasses import dataclass

from agents.llm import DEFAULT_GEMINI_MODEL, DEFAULT_GROQ_MODEL


@dataclass(frozen=True)
class Provider:
    id: str
    label: str
    default_model: str
    # Where the user creates a key.
    key_url: str


PROVIDERS: dict[str, Provider] = {
    "groq": Provider("groq", "Groq", DEFAULT_GROQ_MODEL, "https://console.groq.com/keys"),
    "gemini": Provider("gemini", "Google Gemini", DEFAULT_GEMINI_MODEL, "https://aistudio.google.com/apikey"),
}
