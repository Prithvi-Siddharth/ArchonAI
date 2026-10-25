"""Shared rules for turning a workflow failure into a client-safe error.

Used by both the synchronous endpoint (which raises it as an HTTP error) and
the background job runner (which stores it on the failed job), so the same
failure always gets the same status code and message wherever it happens.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import status
from groq import APIConnectionError, APIStatusError, APITimeoutError, RateLimitError

from agents.llm import LLMInvocationError, MissingAPIKeyError


@dataclass(frozen=True)
class WorkflowFailure:
    """A classified failure: what to tell the client, and whether retrying could help."""

    status_code: int
    message: str
    # True only for temporary problems (rate limits, timeouts, network
    # errors) where running the same job again later may succeed.
    retryable: bool


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


def classify_workflow_error(exc: BaseException) -> WorkflowFailure:
    """Classify a workflow failure with a generic, safe message.

    Checks the most specific causes first (a rate limit wrapped in an
    LLMInvocationError should still surface as 429, not 502). The raw
    exception text is never included -- provider error bodies can contain
    request details -- callers should log the exception server-side instead.
    """
    chain = _cause_chain(exc)

    def has(*types: type[BaseException]) -> bool:
        return any(isinstance(link, types) for link in chain)

    if has(MissingAPIKeyError):
        return WorkflowFailure(status.HTTP_503_SERVICE_UNAVAILABLE, "LLM provider is not configured.", False)
    if has(RateLimitError) or any(isinstance(link, APIStatusError) and link.status_code == 413 for link in chain):
        return WorkflowFailure(
            status.HTTP_429_TOO_MANY_REQUESTS, "LLM provider rate limit reached. Please retry later.", True
        )
    if has(APITimeoutError):
        return WorkflowFailure(status.HTTP_504_GATEWAY_TIMEOUT, "LLM provider timed out. Please retry later.", True)
    if has(APIConnectionError):
        return WorkflowFailure(status.HTTP_502_BAD_GATEWAY, "LLM provider error. Please retry later.", True)
    if has(LLMInvocationError, APIStatusError):
        return WorkflowFailure(status.HTTP_502_BAD_GATEWAY, "LLM provider error. Please retry later.", False)
    return WorkflowFailure(status.HTTP_500_INTERNAL_SERVER_ERROR, "Internal server error.", False)
