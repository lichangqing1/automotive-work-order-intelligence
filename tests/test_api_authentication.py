from __future__ import annotations

import hashlib
import io
import json
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from automotive_quality.api import dashboard_client as api_client
from automotive_quality.api import v1
from automotive_quality.api.auth import (
    AuthConfigurationError,
    BearerAuthenticator,
    get_bearer_authenticator,
)
from automotive_quality.api.dependencies import database_session
from automotive_quality.api.main import app
from automotive_quality.shared.config import Settings, get_settings

VALID_TOKEN = "security-test-token-with-at-least-32-randomish-characters"
ROTATED_TOKEN = "rotated-security-test-token-with-at-least-32-characters"


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _configuration(*credentials: dict[str, object]) -> str:
    return json.dumps([{
        "principal_id": "security-test-principal",
        "category": "test",
        "roles": ["operator", "reviewer"],
        "credentials": list(credentials),
    }])


def _credential(
    token: str,
    key_id: str,
    *,
    enabled: bool = True,
    expires_at: datetime | None = None,
) -> dict[str, object]:
    return {
        "key_id": key_id,
        "token_sha256": _digest(token),
        "enabled": enabled,
        "expires_at": expires_at.isoformat() if expires_at else None,
    }


@pytest.fixture(autouse=True)
def isolated_authentication_cache(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("API_AUTH_PRINCIPALS_JSON", _configuration(_credential(VALID_TOKEN, "active")))
    get_settings.cache_clear()
    get_bearer_authenticator.cache_clear()
    yield
    get_settings.cache_clear()
    get_bearer_authenticator.cache_clear()


def _headers(token: str = VALID_TOKEN) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_liveness_is_public_but_v1_requires_credentials() -> None:
    with TestClient(app) as client:
        assert client.get("/health/live").status_code == 200
        response = client.get("/api/v1/metrics/overview")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize("authorization", ["Bearer invalid-token", "Basic abc", "Bearer"])
def test_invalid_or_malformed_credentials_are_rejected_consistently(authorization: str) -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/metrics/overview", headers={"Authorization": authorization})
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid or missing bearer credential"}
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize(
    ("credential", "token"),
    [
        (_credential(VALID_TOKEN, "disabled", enabled=False), VALID_TOKEN),
        (
            _credential(
                VALID_TOKEN,
                "expired",
                expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
            ),
            VALID_TOKEN,
        ),
    ],
)
def test_disabled_and_expired_credentials_are_rejected(
    monkeypatch: pytest.MonkeyPatch,
    credential: dict[str, object],
    token: str,
) -> None:
    monkeypatch.setenv("API_AUTH_PRINCIPALS_JSON", _configuration(credential))
    get_settings.cache_clear()
    get_bearer_authenticator.cache_clear()
    with TestClient(app) as client:
        response = client.get("/api/v1/metrics/overview", headers=_headers(token))
    assert response.status_code == 401


def test_valid_principal_and_overlapping_rotation_credentials() -> None:
    config = _configuration(
        _credential(VALID_TOKEN, "old-key"),
        _credential(ROTATED_TOKEN, "new-key"),
    )
    parsed = json.loads(config)
    assert parsed[0]["principal_id"] == "security-test-principal"
    verifier = BearerAuthenticator.from_settings(Settings(api_auth_principals_json=config))
    old_principal = verifier.authenticate(VALID_TOKEN)
    new_principal = verifier.authenticate(ROTATED_TOKEN)
    assert old_principal is not None and old_principal.key_id == "old-key"
    assert new_principal is not None and new_principal.key_id == "new-key"
    assert new_principal.principal_id == "security-test-principal"
    assert new_principal.roles == frozenset({"operator", "reviewer"})


def test_missing_or_malformed_configuration_fails_closed_without_secret_disclosure(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret_marker = "credential-value-that-must-not-be-reflected"
    monkeypatch.setenv("API_AUTH_PRINCIPALS_JSON", secret_marker)
    get_settings.cache_clear()
    get_bearer_authenticator.cache_clear()
    with TestClient(app) as client:
        response = client.get("/api/v1/metrics/overview", headers=_headers(secret_marker))
    assert response.status_code == 503
    assert response.json() == {"detail": "API authentication is unavailable"}
    assert secret_marker not in response.text
    assert secret_marker not in caplog.text

    monkeypatch.delenv("API_AUTH_PRINCIPALS_JSON")
    get_settings.cache_clear()
    get_bearer_authenticator.cache_clear()
    with TestClient(app) as client:
        assert client.get("/api/v1/metrics/overview", headers=_headers()).status_code == 503


def test_shared_environment_rejects_missing_configuration() -> None:
    with pytest.raises(ValidationError, match="API authentication configuration is required"):
        Settings(environment="production", api_auth_principals_json=None)


def test_invalid_configuration_redacts_input_and_rejects_ambiguous_credentials() -> None:
    secret_marker = "raw-secret-must-not-appear"
    with pytest.raises(AuthConfigurationError) as malformed:
        BearerAuthenticator.from_settings(Settings(api_auth_principals_json=f'{{"token":"{secret_marker}"}}'))
    assert secret_marker not in str(malformed.value)
    assert malformed.value.__cause__ is None

    duplicated_digest = _configuration(
        _credential(VALID_TOKEN, "first-key"),
        _credential(VALID_TOKEN, "second-key"),
    )
    with pytest.raises(AuthConfigurationError, match="ambiguous credential digests"):
        BearerAuthenticator.from_settings(Settings(api_auth_principals_json=duplicated_digest))

    duplicated_principals = json.dumps([
        {
            "principal_id": "duplicate",
            "credentials": [_credential(VALID_TOKEN, "first-key")],
        },
        {
            "principal_id": "duplicate",
            "credentials": [_credential(ROTATED_TOKEN, "second-key")],
        },
    ])
    with pytest.raises(AuthConfigurationError, match="duplicate principal IDs"):
        BearerAuthenticator.from_settings(Settings(api_auth_principals_json=duplicated_principals))


def test_rejection_occurs_before_database_ai_review_or_jira_side_effects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = {"database": 0, "ai": 0, "workflow": 0, "jira": 0}

    def forbidden_database():
        calls["database"] += 1
        raise AssertionError("database dependency must not execute")
        yield

    def forbidden(name: str):
        def fail(*args, **kwargs):
            del args, kwargs
            calls[name] += 1
            raise AssertionError(f"{name} must not execute")
        return fail

    previous_database_override = app.dependency_overrides.get(database_session)
    app.dependency_overrides[database_session] = forbidden_database
    monkeypatch.setattr(v1, "_ai_workflow", forbidden("ai"))
    monkeypatch.setattr(v1, "_testing_workflow", forbidden("workflow"))
    monkeypatch.setattr(v1, "_issue_tracker", forbidden("jira"))
    try:
        with TestClient(app) as client:
            responses = [
                client.post("/api/v1/ai/requirements/analyze", json={"requirement": "should not run"}),
                client.post("/api/v1/reviews/review-id/decision", json={"status": "Approved", "reviewer": "untrusted"}),
                client.post("/api/v1/requirements/import/jira", json={"issue_key": "NOPE-1"}),
            ]
    finally:
        if previous_database_override is None:
            app.dependency_overrides.pop(database_session, None)
        else:
            app.dependency_overrides[database_session] = previous_database_override
    assert [response.status_code for response in responses] == [401, 401, 401]
    assert calls == {"database": 0, "ai": 0, "workflow": 0, "jira": 0}


def test_readiness_requires_authentication_and_accepts_authorized_internal_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def execute(self, statement):
            del statement

    class Engine:
        def connect(self):
            return Connection()

    monkeypatch.setattr("automotive_quality.api.main.get_engine", lambda: Engine())
    with TestClient(app) as client:
        rejected = client.get("/health/ready")
        accepted = client.get("/health/ready", headers=_headers())
    assert rejected.status_code == 401
    assert accepted.status_code == 200
    assert accepted.json() == {"status": "ready", "database": "ok"}


def test_streamlit_client_sends_server_side_bearer_and_redacts_401(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, str | None] = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self) -> bytes:
            return b'{"status":"ok"}'

    def successful_urlopen(request, timeout):
        captured["authorization"] = request.get_header("Authorization")
        assert timeout == 15
        return Response()

    monkeypatch.setattr(api_client, "urlopen", successful_urlopen)
    assert api_client.request_api("http://api", VALID_TOKEN, "/api/v1/example") == {"status": "ok"}
    assert captured["authorization"] == f"Bearer {VALID_TOKEN}"

    def unauthorized(request, timeout):
        del request, timeout
        raise HTTPError("http://api", 401, f"rejected {VALID_TOKEN}", {}, io.BytesIO())

    monkeypatch.setattr(api_client, "urlopen", unauthorized)
    with pytest.raises(api_client.ApiAuthenticationError) as exc_info:
        api_client.request_api("http://api", VALID_TOKEN, "/api/v1/example")
    assert VALID_TOKEN not in str(exc_info.value)
