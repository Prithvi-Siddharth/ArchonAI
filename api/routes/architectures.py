"""Architecture endpoints.

Deliberately thin: validate the request (via api/schemas.py), run the
existing LangGraph workflow unchanged, and serialize the result. All design,
analysis, and critique logic stays in agents/ and graph/.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status
from groq import APIConnectionError, APIStatusError, APITimeoutError, RateLimitError

from agents.llm import LLMInvocationError, MissingAPIKeyError
from api.examples import load_example_prompts
from api.schemas import ArchitectureRequest, ArchitectureResponse, ErrorResponse, ExamplePrompt
from graph.workflow import WorkflowError, run_workflow

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/architectures", tags=["architectures"])


def _cause_chain(exc: BaseException) -> list[BaseException]:
    """The exception plus everything it was raised from.

    run_workflow wraps every failure as WorkflowError(...) from <original>,
    and invoke_structured in turn wraps provider errors as
    LLMInvocationError(...) from <groq error> -- the real reason a run failed
    is usually two links down.
    """
    chain: list[BaseException] = []
    current: BaseException | None = exc
    while current is not None and current not in chain:
        chain.append(current)
        current = current.__cause__ or current.__context__
    return chain


def _to_http_error(exc: WorkflowError) -> HTTPException:
    """Map a workflow failure to an HTTP error with a generic, safe message.

    Checks the most specific causes first (a rate limit wrapped in an
    LLMInvocationError should still surface as 429, not 502). The raw
    exception text is never returned -- provider error bodies can contain
    request details -- it's only logged server-side.
    """
    chain = _cause_chain(exc)

    def has(*types: type[BaseException]) -> bool:
        return any(isinstance(link, types) for link in chain)

    if has(MissingAPIKeyError):
        return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "LLM provider is not configured.")
    if has(RateLimitError) or any(isinstance(link, APIStatusError) and link.status_code == 413 for link in chain):
        return HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "LLM provider rate limit reached. Please retry later.")
    if has(APITimeoutError):
        return HTTPException(status.HTTP_504_GATEWAY_TIMEOUT, "LLM provider timed out. Please retry later.")
    if has(LLMInvocationError, APIConnectionError, APIStatusError):
        return HTTPException(status.HTTP_502_BAD_GATEWAY, "LLM provider error. Please retry later.")
    return HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Internal server error.")


@router.get("/examples", response_model=list[ExamplePrompt])
def list_examples() -> list[dict[str, str]]:
    """Example prompts that can be sent to POST /api/v1/architectures."""
    return load_example_prompts()


_ERROR_RESPONSES = {
    code: {"model": ErrorResponse}
    for code in (
        status.HTTP_429_TOO_MANY_REQUESTS,
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        status.HTTP_502_BAD_GATEWAY,
        status.HTTP_503_SERVICE_UNAVAILABLE,
        status.HTTP_504_GATEWAY_TIMEOUT,
    )
}


# A plain `def` (not `async def`): run_workflow blocks for minutes on LLM
# calls, so FastAPI runs it in its threadpool instead of on the event loop,
# keeping other requests (e.g. /health) responsive during a run.
@router.post("", response_model=ArchitectureResponse, responses=_ERROR_RESPONSES)
def create_architecture(request: ArchitectureRequest) -> ArchitectureResponse:
    """Run the full multi-agent workflow and return the architecture and final report.

    Synchronous: the request stays open until the run finishes, which
    typically takes a few minutes.
    """
    try:
        final_state = run_workflow(request.user_request)
    except WorkflowError as exc:
        logger.exception("ArchonAI workflow failed")
        raise _to_http_error(exc) from exc
    return ArchitectureResponse.from_state(final_state)
