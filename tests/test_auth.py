"""Tests for accounts and JWT sign-in (auth/ + /api/v1/auth).

In-memory SQLite and a test-only secret: no MySQL, Redis, Groq or real
accounts are touched. Password hashing uses cheaper scrypt parameters for
speed, except in the test that checks the real parameters.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from api.main import app
from auth import passwords, repository
from auth.config import COOKIE_NAME, JWT_ALGORITHM, JWT_ISSUER, get_auth_settings
from auth.models import User
from auth.tokens import create_access_token, read_access_token
from jobs import db

AUTH = "/api/v1/auth"
TEST_SECRET = "test-secret-" + "x" * 40
EMAIL = "Ada@Example.com"
PASSWORD = "correct horse battery"


@pytest.fixture(autouse=True)
def auth_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite://")
    monkeypatch.setenv("JWT_SECRET", TEST_SECRET)
    monkeypatch.delenv("JWT_EXPIRE_MINUTES", raising=False)
    monkeypatch.delenv("COOKIE_SECURE", raising=False)
    monkeypatch.setattr(passwords, "SCRYPT_N", 2**10)
    monkeypatch.setattr(passwords, "SCRYPT_P", 1)
    db.reset_engine()
    yield
    db.reset_engine()


@pytest.fixture
def client():
    # A fresh client per test, so no cookie leaks between tests.
    return TestClient(app)


def _register(client, email=EMAIL, password=PASSWORD):
    return client.post(f"{AUTH}/register", json={"email": email, "password": password})


def _set_cookie_header(response) -> str:
    return response.headers.get("set-cookie", "")


def _token(user_id: str, **overrides) -> str:
    now = datetime.now(timezone.utc)
    claims = {"sub": user_id, "tv": 0, "iat": now, "exp": now + timedelta(hours=1), "iss": JWT_ISSUER, **overrides}
    return jwt.encode(claims, TEST_SECRET, algorithm=JWT_ALGORITHM)


# --- Register ---------------------------------------------------------------------


def test_register_creates_account_signs_in_and_sets_a_safe_cookie(client):
    response = _register(client)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["email"] == "ada@example.com"  # trimmed + lowercased
    assert set(body) == {"id", "email", "display_name", "created_at"}  # never the hash
    cookie = _set_cookie_header(response).lower()
    assert cookie.startswith(f"{COOKIE_NAME}=")
    for part in ("httponly", "samesite=strict", "path=/api", "max-age=28800"):
        assert part in cookie
    assert "secure" not in cookie.replace("samesite", "")  # plain-HTTP localhost by default

    me = client.get(f"{AUTH}/me")
    assert me.status_code == 200
    assert me.json() == body


def test_secure_cookie_and_custom_lifetime_from_env(client, monkeypatch):
    monkeypatch.setenv("COOKIE_SECURE", "true")
    monkeypatch.setenv("JWT_EXPIRE_MINUTES", "60")
    cookie = _set_cookie_header(_register(client)).lower()
    assert "; secure" in cookie
    assert "max-age=3600" in cookie


def test_password_is_stored_only_as_a_scrypt_hash(client):
    _register(client)
    user = repository.get_user_by_email("ada@example.com")
    assert user is not None
    assert user.password_hash.startswith("scrypt$")
    assert PASSWORD not in user.password_hash
    assert passwords.verify_password(PASSWORD, user.password_hash)
    assert not passwords.verify_password("wrong password", user.password_hash)


def test_real_scrypt_parameters_and_unique_salts(monkeypatch):
    monkeypatch.undo()  # the real N=2^15, r=8, p=3
    first, second = passwords.hash_password(PASSWORD), passwords.hash_password(PASSWORD)
    assert first.split("$")[:4] == ["scrypt", str(2**15), "8", "3"]
    assert first != second  # random salt per hash
    assert passwords.verify_password(PASSWORD, first) and passwords.verify_password(PASSWORD, second)


@pytest.mark.parametrize("stored", ["", "plain", "bcrypt$1$2$3$4$5", "scrypt$x$8$1$AAAA$AAAA", "scrypt$1024$8$1$!!$!!"])
def test_malformed_stored_hashes_never_match(stored):
    assert passwords.verify_password(PASSWORD, stored) is False


def test_duplicate_email_is_rejected_case_insensitively(client):
    assert _register(client).status_code == 201
    again = _register(TestClient(app), email="  ADA@example.COM ")
    assert again.status_code == 409
    assert again.json() == {"detail": "An account with this email already exists."}


@pytest.mark.parametrize(
    "body",
    [
        {"email": "not-an-email", "password": PASSWORD},
        {"email": "a b@example.com", "password": PASSWORD},
        {"email": "ada@example.com", "password": "short"},
        {"email": "ada@example.com", "password": "x" * 129},
        {"email": "ada@example.com"},
        {"password": PASSWORD},
    ],
)
def test_register_validation(client, body):
    response = client.post(f"{AUTH}/register", json=body)
    assert response.status_code == 422
    assert COOKIE_NAME not in _set_cookie_header(response)


# --- Login / logout / me -----------------------------------------------------------


def test_login_with_correct_credentials_sets_cookie(client):
    _register(client)
    fresh = TestClient(app)
    response = fresh.post(f"{AUTH}/login", json={"email": " ADA@example.com", "password": PASSWORD})
    assert response.status_code == 200
    assert response.json()["email"] == "ada@example.com"
    assert "httponly" in _set_cookie_header(response).lower()
    assert fresh.get(f"{AUTH}/me").status_code == 200


def test_wrong_password_and_unknown_email_get_the_same_answer(client):
    _register(client)
    fresh = TestClient(app)
    wrong = fresh.post(f"{AUTH}/login", json={"email": EMAIL, "password": "wrong password"})
    unknown = fresh.post(f"{AUTH}/login", json={"email": "nobody@example.com", "password": PASSWORD})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json() == {"detail": "Invalid email or password."}
    assert COOKIE_NAME not in _set_cookie_header(wrong) + _set_cookie_header(unknown)
    assert fresh.get(f"{AUTH}/me").status_code == 401


def test_logout_clears_the_cookie(client):
    _register(client)
    response = client.post(f"{AUTH}/logout")
    assert response.status_code == 204
    cookie = _set_cookie_header(response).lower()
    assert cookie.startswith(f'{COOKIE_NAME}=""') and "max-age=0" in cookie and "path=/api" in cookie
    assert client.get(f"{AUTH}/me").status_code == 401


def test_logout_works_when_not_signed_in_or_not_configured(client, monkeypatch):
    assert client.post(f"{AUTH}/logout").status_code == 204
    monkeypatch.delenv("JWT_SECRET")
    assert client.post(f"{AUTH}/logout").status_code == 204


def test_me_without_a_cookie_is_401(client):
    response = client.get(f"{AUTH}/me")
    assert response.status_code == 401
    assert response.json() == {"detail": "Not signed in, or the session has expired."}


# --- Token checks ------------------------------------------------------------------


def _me_with(token: str) -> int:
    fresh = TestClient(app)
    fresh.cookies.set(COOKIE_NAME, token, path="/api")
    return fresh.get(f"{AUTH}/me").status_code


def test_a_valid_token_is_accepted(client):
    user_id = _register(client).json()["id"]
    assert _me_with(_token(user_id)) == 200


@pytest.mark.parametrize(
    "make_token",
    [
        pytest.param(lambda uid: _token(uid, exp=datetime.now(timezone.utc) - timedelta(seconds=5)), id="expired"),
        pytest.param(lambda uid: _token(uid, iss="someone-else"), id="wrong-issuer"),
        pytest.param(lambda uid: jwt.encode({"sub": uid, "iat": 1, "exp": 9999999999, "iss": JWT_ISSUER}, "another-secret-" + "y" * 40, algorithm="HS256"), id="other-secret"),
        pytest.param(lambda uid: jwt.encode({"sub": uid, "iat": 1, "exp": 9999999999, "iss": JWT_ISSUER}, TEST_SECRET, algorithm="HS512"), id="other-algorithm"),
        pytest.param(lambda uid: jwt.encode({"sub": uid, "iat": 1, "exp": 9999999999, "iss": JWT_ISSUER}, None, algorithm="none"), id="alg-none"),
        pytest.param(lambda uid: _token(uid)[:-4] + "AAAA", id="tampered-signature"),
        pytest.param(lambda uid: jwt.encode({"iat": 1, "exp": 9999999999, "iss": JWT_ISSUER}, TEST_SECRET, algorithm="HS256"), id="no-subject"),
        pytest.param(lambda uid: _token("00000000-0000-0000-0000-000000000000"), id="unknown-user"),
        pytest.param(lambda uid: jwt.encode({"sub": uid, "iat": 1, "exp": 9999999999, "iss": JWT_ISSUER}, TEST_SECRET, algorithm="HS256"), id="no-token-version"),
        pytest.param(lambda uid: _token(uid, tv="0"), id="token-version-not-a-number"),
        pytest.param(lambda uid: _token(uid, tv=1), id="token-version-from-the-future"),
        pytest.param(lambda uid: "not.a.jwt", id="garbage"),
    ],
)
def test_bad_tokens_are_rejected(client, make_token):
    user_id = _register(client).json()["id"]
    assert _me_with(make_token(user_id)) == 401


def test_token_round_trip_and_expiry_claim():
    settings = get_auth_settings()
    now = datetime.now(timezone.utc)
    token = create_access_token("user-1", settings, now=now)
    assert read_access_token(token, settings) == "user-1"
    claims = jwt.decode(token, TEST_SECRET, algorithms=["HS256"], issuer=JWT_ISSUER)
    assert claims["exp"] - claims["iat"] == 8 * 60 * 60


# --- Configuration and failures ------------------------------------------------------


@pytest.mark.parametrize("secret", [None, "", "too-short-secret"])
def test_without_a_usable_secret_auth_answers_503(client, monkeypatch, secret):
    if secret is None:
        monkeypatch.delenv("JWT_SECRET")
    else:
        monkeypatch.setenv("JWT_SECRET", secret)
    expected = {"detail": "Authentication is not configured."}
    for response in (
        _register(client),
        client.post(f"{AUTH}/login", json={"email": EMAIL, "password": PASSWORD}),
        client.get(f"{AUTH}/me"),
    ):
        assert response.status_code == 503
        assert response.json() == expected
    # Nothing was stored: register refused before creating the account.
    monkeypatch.setenv("JWT_SECRET", TEST_SECRET)
    assert repository.get_user_by_email("ada@example.com") is None


def test_account_store_errors_are_503_without_details(client, monkeypatch, caplog):
    def broken(*args, **kwargs):
        raise OperationalError(f"INSERT ... {PASSWORD}", {"email": EMAIL}, Exception("db down"))

    monkeypatch.setattr(repository, "create_user", broken)
    monkeypatch.setattr(repository, "get_user_by_email", broken)
    with caplog.at_level(logging.INFO):
        register = _register(client)
        login = client.post(f"{AUTH}/login", json={"email": EMAIL, "password": PASSWORD})
    for response in (register, login):
        assert response.status_code == 503
        assert response.json() == {"detail": "Account store is unavailable. Please retry later."}
    assert PASSWORD not in caplog.text and "db down" not in caplog.text


def test_password_never_reaches_the_logs(client, caplog):
    with caplog.at_level(logging.DEBUG):
        _register(client)
        TestClient(app).post(f"{AUTH}/login", json={"email": EMAIL, "password": PASSWORD})
        TestClient(app).post(f"{AUTH}/login", json={"email": EMAIL, "password": "wrong password"})
    assert PASSWORD not in caplog.text
    assert "wrong password" not in caplog.text


def test_bad_boolean_setting_fails_loudly(monkeypatch):
    monkeypatch.setenv("COOKIE_SECURE", "ture")
    with pytest.raises(ValueError, match="COOKIE_SECURE"):
        get_auth_settings()


# --- Nothing else changed ------------------------------------------------------------


def test_existing_public_endpoints_still_work_signed_out(client):
    assert client.get("/health").status_code == 200
    assert client.get("/api/v1/architectures/examples").status_code == 200


def test_users_table_is_created_next_to_the_job_table(client):
    _register(client)
    from sqlalchemy import inspect

    tables = set(inspect(db.get_engine()).get_table_names())
    assert {"users", "architecture_jobs"} <= tables
    assert "password_hash" in {c["name"] for c in inspect(db.get_engine()).get_columns(User.__tablename__)}
