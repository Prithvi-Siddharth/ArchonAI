"""ArchonAI -- Multi-Agent Cloud Architecture Designer, REST API.

FastAPI entry point. Run locally with:

    uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

Interactive API docs are served at /docs.
"""

from __future__ import annotations

import logging

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from api.routes import architectures, auth, llm_settings
from api.schemas import HealthResponse
from graph.cloudwatch_logs import configure_cloudwatch_logging

# override=True so a .env edit is picked up on a --reload restart even if the
# variable was already set in the shell (matches the previous Streamlit app).
load_dotenv(override=True)

# Without a handler on the root logger, logger.exception() in the routes
# would only reach stderr via Python's bare last-resort handler.
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

# Also ship logs to CloudWatch (/archonai/api) when CLOUDWATCH_ENABLED=true.
# Console logging above is unaffected either way.
configure_cloudwatch_logging("api")

app = FastAPI(
    title="ArchonAI",
    description=(
        "A LangGraph-orchestrated team of agents that analyzes requirements, designs an AWS "
        "architecture, critiques it, and revises it until it holds up."
    ),
    version="1.0.0",
)

app.include_router(architectures.router)
app.include_router(auth.router)
app.include_router(llm_settings.router)


@app.exception_handler(RequestValidationError)
async def _validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
    """FastAPI's usual 422, minus each error's `input`: it would echo the submitted value
    back, which for passwords and API keys is a secret that should not travel twice."""
    errors = [{key: value for key, value in error.items() if key != "input"} for error in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": jsonable_encoder(errors)})


@app.get("/health", response_model=HealthResponse, tags=["health"])
def health() -> HealthResponse:
    """Liveness check. Does not call the LLM provider or reveal configuration."""
    return HealthResponse()
