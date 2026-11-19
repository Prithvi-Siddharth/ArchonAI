"""Bring your own key: encrypted storage, the settings endpoints, and using the key in a job.

In-memory SQLite, test-only secrets and fake keys. No provider is ever called:
the LLM layer is replaced by the same fake the workflow tests use, and it only
records which credentials were active when an agent asked for a model.
"""

from __future__ import annotations

import logging

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import OperationalError

import agents.llm as llm_module
from agents.llm import LLMCredentials, is_credential_rejection, use_llm_credentials
from api.errors import KEY_REJECTED_MESSAGE, KEY_UNUSABLE_MESSAGE, classify_workflow_error
from api.main import app
from auth import passwords
from jobs import db, repository as job_repository
from jobs.models import JobStatus
from jobs.runner import execute_job
from llm_keys import crypto, repository, service
from llm_keys.config import MIN_SECRET_LENGTH, get_encryption_secret
from llm_keys.models import UserLLMSettings
from llm_keys.service import StoredKeyUnusableError

from .test_graph import _patch_llm

URL = "/api/v1/settings/llm"
JWT_SECRET = "test-secret-" + "x" * 40
ENC_SECRET = "enc-secret-" + "y" * 40
OTHER_ENC_SECRET = "other-enc-" + "z" * 40
KEY = "gsk_TESTKEY1234567890abcdef"
OTHER_KEY = "AIzaSyFAKEKEY0987654321zyxwvu"


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("JWT_SECRET", JWT_SECRET)
    monkeypatch.setenv("KEY_ENCRYPTION_SECRET", ENC_SECRET)
    monkeypatch.setattr(passwords, "SCRYPT_N", 2**10)
    monkeypatch.setattr(passwords, "SCRYPT_P", 1)
    db.reset_engine()
    yield
    db.reset_engine()


def _user(email: str = "ada@example.com") -> tuple[TestClient, str]:
    client = TestClient(app)
    response = client.post("/api/v1/auth/register", json={"email": email, "password": "test password"})
    assert response.status_code == 201, response.text
    return client, response.json()["id"]


def _save(client: TestClient, **body):
    return client.put(URL, json={"provider": "groq", "api_key": KEY, **body})


# --- Encryption --------------------------------------------------------------


def test_encrypted_token_round_trips_and_does_not_contain_the_key():
    token = crypto.encrypt_key(KEY, "user-1", ENC_SECRET)
    assert KEY not in token and KEY[-8:] not in token
    assert crypto.decrypt_key(token, "user-1", ENC_SECRET) == KEY


def test_encryption_is_randomised_per_call():
    assert crypto.encrypt_key(KEY, "user-1", ENC_SECRET) != crypto.encrypt_key(KEY, "user-1", ENC_SECRET)


def test_token_is_refused_under_another_secret_another_user_or_damage():
    token = crypto.encrypt_key(KEY, "user-1", ENC_SECRET)
    assert crypto.decrypt_key(token, "user-1", OTHER_ENC_SECRET) is None
    assert crypto.decrypt_key(token, "user-2", ENC_SECRET) is None  # a row copied onto another user
    assert crypto.decrypt_key(token[:-4] + "AAAA", "user-1", ENC_SECRET) is None
    assert crypto.decrypt_key("not a token", "user-1", ENC_SECRET) is None


def test_short_or_missing_secret_means_keys_cannot_be_saved(monkeypatch):
    monkeypatch.setenv("KEY_ENCRYPTION_SECRET", "x" * (MIN_SECRET_LENGTH - 1))
    assert get_encryption_secret() is None
    monkeypatch.delenv("KEY_ENCRYPTION_SECRET")
    assert get_encryption_secret() is None
    monkeypatch.setenv("KEY_ENCRYPTION_SECRET", "x" * MIN_SECRET_LENGTH)
    assert get_encryption_secret() == "x" * MIN_SECRET_LENGTH


# --- Endpoints: access -------------------------------------------------------


@pytest.mark.parametrize("method", ["get", "put", "delete"])
def test_signed_out_requests_are_401(method):
    client = TestClient(app)
    kwargs = {"json": {"provider": "groq", "api_key": KEY}} if method == "put" else {}
    assert getattr(client, method)(URL, **kwargs).status_code == 401


def test_nothing_is_configured_at_first_and_providers_are_listed():
    client, _ = _user()
    body = client.get(URL).json()
    assert body["configured"] is False
    assert body["provider"] is None and body["key_hint"] is None
    assert body["encryption_available"] is True
    assert [p["id"] for p in body["providers"]] == ["groq", "gemini"]
    assert all(p["default_model"] and p["key_url"].startswith("https://") for p in body["providers"])


# --- Endpoints: saving -------------------------------------------------------


def test_saving_returns_the_hint_but_never_the_key():
    client, _ = _user()
    response = _save(client, model="llama-3.3-70b")
    assert response.status_code == 200
    body = response.json()
    assert body["configured"] is True
    assert (body["provider"], body["model"], body["key_hint"]) == ("groq", "llama-3.3-70b", KEY[-4:])
    assert KEY not in response.text
    assert KEY not in client.get(URL).text


def test_the_key_is_stored_encrypted_never_in_plain_text():
    client, user_id = _user()
    _save(client)
    with db.session_scope() as session:
        row = session.execute(select(UserLLMSettings)).scalar_one()
        everything = str(session.execute(text("select * from user_llm_settings")).all())
    assert row.user_id == user_id
    assert KEY not in row.encrypted_key and KEY not in everything
    assert crypto.decrypt_key(row.encrypted_key, user_id, ENC_SECRET) == KEY


def test_replacing_the_key_and_provider_updates_the_one_row():
    client, _ = _user()
    _save(client)
    response = client.put(URL, json={"provider": "gemini", "api_key": OTHER_KEY})
    assert response.json()["provider"] == "gemini"
    assert response.json()["key_hint"] == OTHER_KEY[-4:]
    assert response.json()["model"] is None
    with db.session_scope() as session:
        assert len(session.execute(select(UserLLMSettings)).all()) == 1


def test_blank_model_means_the_providers_default():
    client, _ = _user()
    assert _save(client, model="   ").json()["model"] is None


def test_changing_only_the_model_keeps_the_saved_key():
    client, user_id = _user()
    _save(client)
    response = client.put(URL, json={"provider": "groq", "model": "other-model"})
    assert response.status_code == 200
    assert response.json()["model"] == "other-model" and response.json()["key_hint"] == KEY[-4:]
    assert service.credentials_for(user_id) == LLMCredentials("groq", KEY, "other-model")


def test_a_key_is_required_for_the_first_save_and_when_the_provider_changes():
    client, _ = _user()
    first = client.put(URL, json={"provider": "groq", "model": "m"})
    assert first.status_code == 422
    assert first.json()["detail"][0]["loc"] == ["body", "api_key"]
    _save(client)
    switched = client.put(URL, json={"provider": "gemini"})
    assert switched.status_code == 422
    assert client.get(URL).json()["provider"] == "groq"  # unchanged


def test_without_an_encryption_secret_saving_is_503_and_stores_nothing(monkeypatch):
    client, _ = _user()
    monkeypatch.delenv("KEY_ENCRYPTION_SECRET")
    response = _save(client)
    assert response.status_code == 503
    assert response.json() == {"detail": "Saving API keys is not configured on the server."}
    assert client.get(URL).json()["encryption_available"] is False
    with db.session_scope() as session:
        assert session.execute(select(UserLLMSettings)).first() is None


@pytest.mark.parametrize(
    "body, field",
    [
        ({"provider": "openai", "api_key": KEY}, "provider"),
        ({"provider": "groq", "api_key": "short"}, "api_key"),
        ({"provider": "groq", "api_key": "x" * 513}, "api_key"),
        ({"provider": "groq", "api_key": "has space inside1234"}, "api_key"),
        ({"provider": "groq", "api_key": "line\nbreak1234567"}, "api_key"),
        ({"provider": "groq", "api_key": KEY, "model": "bad model!"}, "model"),
        ({"provider": "groq", "api_key": KEY, "model": "m" * 101}, "model"),
        ({"provider": "groq", "api_key": 12345678}, "api_key"),
        ({}, "provider"),
    ],
)
def test_invalid_input_is_422_and_nothing_is_stored(body, field):
    client, _ = _user()
    response = client.put(URL, json=body)
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", field]
    assert client.get(URL).json()["configured"] is False


def test_a_rejected_key_is_not_echoed_back_in_the_422():
    client, _ = _user()
    bad_key = "bad key with spaces 12345"
    response = client.put(URL, json={"provider": "groq", "api_key": bad_key})
    assert response.status_code == 422
    assert bad_key not in response.text and "input" not in response.text


def test_other_endpoints_no_longer_echo_submitted_values_in_a_422():
    response = TestClient(app).post("/api/v1/auth/register", json={"email": "ada@example.com", "password": "short12"})
    assert response.status_code == 422
    assert "short12" not in response.text
    item = response.json()["detail"][0]
    assert set(item) >= {"type", "loc", "msg"} and "input" not in item


# --- Endpoints: removing, isolation ------------------------------------------


def test_deleting_removes_the_key_and_is_safe_to_repeat():
    client, user_id = _user()
    _save(client)
    assert client.delete(URL).status_code == 204
    assert client.get(URL).json()["configured"] is False
    assert service.credentials_for(user_id) is None
    assert client.delete(URL).status_code == 204


def test_each_user_sees_and_changes_only_their_own_settings():
    ada, ada_id = _user("ada@example.com")
    grace, grace_id = _user("grace@example.com")
    _save(ada)
    assert grace.get(URL).json()["configured"] is False
    grace.put(URL, json={"provider": "gemini", "api_key": OTHER_KEY})
    grace.delete(URL)
    assert ada.get(URL).json()["key_hint"] == KEY[-4:]
    assert service.credentials_for(ada_id).api_key == KEY
    assert service.credentials_for(grace_id) is None


def test_a_user_id_sent_by_the_client_is_ignored():
    ada, ada_id = _user("ada@example.com")
    grace, grace_id = _user("grace@example.com")
    _save(ada)
    # Grace tries to write to, and read, Ada's row by naming her.
    grace.put(f"{URL}?user_id={ada_id}", json={"provider": "gemini", "api_key": OTHER_KEY, "user_id": ada_id})
    assert grace.get(f"{URL}?user_id={ada_id}").json()["provider"] == "gemini"
    assert service.credentials_for(ada_id).provider == "groq"
    assert service.credentials_for(grace_id).provider == "gemini"


def test_a_store_outage_is_503_without_leaking_details(monkeypatch, caplog):
    client, _ = _user()

    def broken(*args, **kwargs):
        raise OperationalError("INSERT secret-statement", {"k": KEY}, Exception("secret-driver-detail"))

    monkeypatch.setattr(repository, "save_settings", broken)
    with caplog.at_level(logging.DEBUG):
        response = _save(client)
    assert response.status_code == 503
    assert response.json() == {"detail": "Settings store is unavailable. Please retry later."}
    assert "secret-statement" not in caplog.text and KEY not in caplog.text and "secret-driver-detail" not in caplog.text


def test_the_key_never_appears_in_logs(caplog):
    client, _ = _user()
    with caplog.at_level(logging.DEBUG):
        _save(client)
        client.put(URL, json={"provider": "groq", "api_key": "x y"})
        client.get(URL)
        client.delete(URL)
    assert KEY not in caplog.text and "x y" not in caplog.text
    assert "LLM settings saved" in caplog.text


# --- Using the key in a job --------------------------------------------------


def _record_credentials(monkeypatch) -> list:
    """Run the fake LLM, noting which credentials were active each time an agent asked for a model."""
    _patch_llm(monkeypatch, critic_verdicts=[True])
    fake = llm_module.get_llm
    seen: list = []

    def recording(*args, **kwargs):
        seen.append(llm_module._credentials.get())
        return fake(*args, **kwargs)

    monkeypatch.setattr(llm_module, "get_llm", recording)
    return seen


def _job_for(user_id) -> str:
    return job_repository.create_job("Design a blogging platform for 10,000 users.", owner_id=user_id)


def test_a_job_runs_every_agent_with_its_owners_key_including_parallel_ones(monkeypatch):
    client, user_id = _user()
    _save(client, model="my-model")
    seen = _record_credentials(monkeypatch)

    job_id = _job_for(user_id)
    assert execute_job(job_id) is None

    assert job_repository.get_job(job_id).status is JobStatus.SUCCEEDED
    assert len(seen) >= 12  # every agent that builds a model
    assert set(seen) == {LLMCredentials("groq", KEY, "my-model")}


def test_a_user_without_a_key_runs_on_the_servers_setup(monkeypatch):
    _, user_id = _user()
    seen = _record_credentials(monkeypatch)
    job_id = _job_for(user_id)
    execute_job(job_id)
    assert job_repository.get_job(job_id).status is JobStatus.SUCCEEDED
    assert seen and set(seen) == {None}


def test_another_users_key_is_never_used_for_a_job(monkeypatch):
    ada, _ = _user("ada@example.com")
    _, grace_id = _user("grace@example.com")
    _save(ada)
    seen = _record_credentials(monkeypatch)
    execute_job(_job_for(grace_id))
    assert set(seen) == {None}


def test_credentials_do_not_outlive_the_run(monkeypatch):
    client, user_id = _user()
    _save(client)
    _record_credentials(monkeypatch)
    execute_job(_job_for(user_id))
    assert llm_module._credentials.get() is None


def test_the_key_is_not_in_the_job_row_or_its_result(monkeypatch):
    client, user_id = _user()
    _save(client)
    _record_credentials(monkeypatch)
    job_id = _job_for(user_id)
    execute_job(job_id)
    job = job_repository.get_job(job_id)
    assert KEY not in repr(job.result) and KEY not in repr(job.error_message)
    assert KEY not in client.get(f"/api/v1/architectures/jobs/{job_id}").text


@pytest.mark.parametrize("break_it", ["secret_changed", "secret_removed", "row_moved"])
def test_an_unusable_saved_key_fails_the_job_instead_of_using_the_servers_key(monkeypatch, break_it):
    client, user_id = _user()
    _save(client)
    seen = _record_credentials(monkeypatch)
    if break_it == "secret_changed":
        monkeypatch.setenv("KEY_ENCRYPTION_SECRET", OTHER_ENC_SECRET)
    elif break_it == "secret_removed":
        monkeypatch.delenv("KEY_ENCRYPTION_SECRET")
    else:
        # The stored token was sealed for a different user (a row copied across accounts).
        foreign = crypto.encrypt_key(KEY, "someone-else", ENC_SECRET)
        with db.session_scope() as session:
            session.execute(text("update user_llm_settings set encrypted_key = :t"), {"t": foreign})

    job_id = _job_for(user_id)
    failure = execute_job(job_id, allow_retry=True)

    job = job_repository.get_job(job_id)
    assert job.status is JobStatus.FAILED
    assert (job.error_status_code, job.error_message) == (400, KEY_UNUSABLE_MESSAGE)
    assert failure is not None and failure.retryable is False
    assert seen == []  # no agent ever ran, so the server's key was not touched


def test_credentials_for_a_legacy_job_without_an_owner_is_none():
    assert service.credentials_for(None) is None


# --- get_llm picks the right provider, key and model -------------------------


def _capture_builders(monkeypatch) -> list:
    calls: list = []

    def groq(temperature, max_tokens, *, api_key=None, model=None):
        calls.append(("groq", api_key, model))
        return object()

    def gemini(temperature, max_tokens, *, api_key=None, model=None):
        calls.append(("gemini", api_key, model))
        return object()

    monkeypatch.setattr(llm_module, "_build_groq_llm", groq)
    monkeypatch.setattr(llm_module, "_build_gemini_llm", gemini)
    return calls


def test_get_llm_uses_the_active_credentials_over_the_servers_settings(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "groq")
    calls = _capture_builders(monkeypatch)
    with use_llm_credentials(LLMCredentials("gemini", OTHER_KEY, "gem-model")):
        llm_module.get_llm()
    assert calls == [("gemini", OTHER_KEY, "gem-model")]


def test_get_llm_without_credentials_still_follows_llm_provider(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    calls = _capture_builders(monkeypatch)
    llm_module.get_llm()
    assert calls == [("gemini", None, None)]


def test_the_servers_model_setting_is_not_applied_to_a_users_own_key(monkeypatch):
    monkeypatch.setenv("GROQ_MODEL", "server-model")
    monkeypatch.setenv("GROQ_API_KEY", "server-key-1234567890")
    with use_llm_credentials(LLMCredentials("groq", KEY)):
        own = llm_module.get_llm()
    server = llm_module.get_llm()
    assert own.model_name == llm_module.DEFAULT_GROQ_MODEL
    assert own.groq_api_key.get_secret_value() == KEY
    assert server.model_name == "server-model"
    assert server.groq_api_key.get_secret_value() == "server-key-1234567890"


def test_credentials_repr_hides_the_key():
    assert KEY not in repr(LLMCredentials("groq", KEY, "m")) and KEY not in str(LLMCredentials("groq", KEY, "m"))


def test_use_llm_credentials_with_none_changes_nothing():
    with use_llm_credentials(None):
        assert llm_module._credentials.get() is None


# --- Telling a user their key was refused ------------------------------------


class _ProviderError(Exception):
    def __init__(self, status_code=None, details=None):
        super().__init__("provider said: " + KEY)
        self.status_code = status_code
        self.details = details


@pytest.mark.parametrize("status_code", [401, 403])
def test_a_401_or_403_from_the_provider_is_a_key_rejection(status_code):
    exc = llm_module.LLMInvocationError("x")
    exc.__cause__ = _ProviderError(status_code)
    assert is_credential_rejection(exc)
    failure = classify_workflow_error(exc)
    assert (failure.status_code, failure.message, failure.retryable) == (502, KEY_REJECTED_MESSAGE, False)
    assert KEY not in failure.message


def test_geminis_invalid_key_answer_is_a_key_rejection():
    details = {"error": {"code": 400, "status": "INVALID_ARGUMENT", "details": [{"reason": "API_KEY_INVALID"}]}}
    exc = llm_module.LLMInvocationError("x")
    exc.__cause__ = _ProviderError(400, details)
    assert classify_workflow_error(exc).message == KEY_REJECTED_MESSAGE


@pytest.mark.parametrize("status_code", [None, 400, 404, 500])
def test_other_provider_errors_are_not_mistaken_for_a_rejected_key(status_code):
    assert not is_credential_rejection(_ProviderError(status_code))


def test_an_unusable_stored_key_classifies_as_a_non_retryable_400():
    failure = classify_workflow_error(StoredKeyUnusableError())
    assert (failure.status_code, failure.message, failure.retryable) == (400, KEY_UNUSABLE_MESSAGE, False)
