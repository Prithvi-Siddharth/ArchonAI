"""ArchonAI -- Multi-Agent Cloud Architecture Designer, REST API.

FastAPI entry point. Run locally with:

    uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

Interactive API docs are served at /docs.
"""

from __future__ import annotations

import logging

from dotenv import load_dotenv
from fastapi import FastAPI

from api.routes import architectures
from api.schemas import HealthResponse

# override=True so a .env edit is picked up on a --reload restart even if the
# variable was already set in the shell (matches the previous Streamlit app).
load_dotenv(override=True)

# Without a handler on the root logger, logger.exception() in the routes
# would only reach stderr via Python's bare last-resort handler.
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(
    title="ArchonAI",
    description=(
        "A LangGraph-orchestrated team of agents that analyzes requirements, designs an AWS "
        "architecture, critiques it, and revises it until it holds up."
    ),
    version="1.0.0",
)

app.include_router(architectures.router)


@app.get("/health", response_model=HealthResponse, tags=["health"])
def health() -> HealthResponse:
    """Liveness check. Does not call the LLM provider or reveal configuration."""
    return HealthResponse()
