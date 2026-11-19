"""Bring your own key: save, show and remove the signed-in user's LLM provider key.

The key is encrypted before it is stored and is never returned by any
endpoint, only its last four characters. It is not logged. A user's jobs
read it back inside the worker (llm_keys/service.py); it never travels
through the job row or the queue.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.exc import SQLAlchemyError

from api.schemas import ErrorResponse, LLMProviderOption, LLMSettingsResponse, LLMSettingsUpdate, _as_utc
from auth.dependencies import get_current_user
from auth.models import User
from llm_keys import repository
from llm_keys.config import get_encryption_secret
from llm_keys.crypto import encrypt_key
from llm_keys.models import UserLLMSettings
from llm_keys.providers import PROVIDERS

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/settings/llm", tags=["settings"])

_ERRORS = {
    status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse},
    status.HTTP_503_SERVICE_UNAVAILABLE: {"model": ErrorResponse},
}
_STORE_UNAVAILABLE = HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Settings store is unavailable. Please retry later.")
_ENCRYPTION_UNAVAILABLE = HTTPException(
    status.HTTP_503_SERVICE_UNAVAILABLE, "Saving API keys is not configured on the server."
)
_KEY_REQUIRED = HTTPException(
    422,
    [{"type": "value_error", "loc": ["body", "api_key"], "msg": "Enter your API key for this provider."}],
)


def _store_error(exc: SQLAlchemyError) -> HTTPException:
    # Class name only: SQLAlchemy messages can include statement parameters.
    logger.error("LLM settings store error (%s).", type(exc).__name__)
    return _STORE_UNAVAILABLE


def _response(row: UserLLMSettings | None) -> LLMSettingsResponse:
    providers = [
        LLMProviderOption(id=p.id, label=p.label, default_model=p.default_model, key_url=p.key_url) for p in PROVIDERS.values()
    ]
    encryption_available = get_encryption_secret() is not None
    if row is None:
        return LLMSettingsResponse(configured=False, encryption_available=encryption_available, providers=providers)
    return LLMSettingsResponse(
        configured=True,
        provider=row.provider,
        model=row.model,
        key_hint=row.key_hint,
        updated_at=_as_utc(row.updated_at),
        encryption_available=encryption_available,
        providers=providers,
    )


@router.get("", response_model=LLMSettingsResponse, responses=_ERRORS)
def get_llm_settings(user: User = Depends(get_current_user)) -> LLMSettingsResponse:
    """The signed-in user's saved provider, model and key hint (never the key)."""
    try:
        return _response(repository.get_settings(user.id))
    except SQLAlchemyError as exc:
        raise _store_error(exc) from None


@router.put("", response_model=LLMSettingsResponse, responses={**_ERRORS, 422: {"model": ErrorResponse}})
def save_llm_settings(body: LLMSettingsUpdate, user: User = Depends(get_current_user)) -> LLMSettingsResponse:
    """Save a provider and key, or (with no `api_key`) change only the model of the saved key."""
    try:
        if body.api_key is None:
            existing = repository.get_settings(user.id)
            # A key is required for a first save, and whenever the provider changes.
            if existing is None or existing.provider != body.provider:
                raise _KEY_REQUIRED
            row = repository.update_model(user.id, body.model)
        else:
            secret = get_encryption_secret()
            if secret is None:
                raise _ENCRYPTION_UNAVAILABLE
            row = repository.save_settings(
                user.id,
                provider=body.provider,
                encrypted_key=encrypt_key(body.api_key, user.id, secret),
                key_hint=body.api_key[-4:],
                model=body.model,
            )
    except SQLAlchemyError as exc:
        raise _store_error(exc) from None
    # Never the key: only who, and which provider.
    logger.info("LLM settings saved (user %s, provider %s).", user.id, body.provider)
    return _response(row)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT, responses=_ERRORS)
def delete_llm_settings(user: User = Depends(get_current_user)) -> Response:
    """Remove the saved key. Later jobs use the server's own provider again. Safe to repeat."""
    try:
        removed = repository.delete_settings(user.id)
    except SQLAlchemyError as exc:
        raise _store_error(exc) from None
    if removed:
        logger.info("LLM key removed (user %s).", user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
