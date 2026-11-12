from __future__ import annotations

import hashlib
import json
import os

import pytest

# A developer's .env may intentionally enable live Jira/OpenAI integrations.
# The default test suite must remain offline; opt-in integration tests construct
# their real clients directly from the dedicated environment variables.
os.environ["ISSUE_TRACKER"] = "local"
os.environ["LLM_PROVIDER"] = "mock"

# Deliberately synthetic and scoped to the test process. Security tests remove
# or replace this configuration when exercising failure paths.
TEST_API_TOKEN = "test-only-operator-token-with-no-production-value"
TEST_REVIEWER_TOKEN = "test-only-reviewer-token-with-no-production-value"
TEST_READER_TOKEN = "test-only-reader-token-with-no-production-value"
TEST_ADMIN_TOKEN = "test-only-administrator-token-with-no-production-value"
TEST_DUAL_ROLE_TOKEN = "test-only-dual-role-token-with-no-production-value"
TEST_AUTH_HEADERS = {"Authorization": f"Bearer {TEST_API_TOKEN}"}
TEST_REVIEWER_HEADERS = {"Authorization": f"Bearer {TEST_REVIEWER_TOKEN}"}
TEST_READER_HEADERS = {"Authorization": f"Bearer {TEST_READER_TOKEN}"}
TEST_ADMIN_HEADERS = {"Authorization": f"Bearer {TEST_ADMIN_TOKEN}"}
TEST_DUAL_ROLE_HEADERS = {"Authorization": f"Bearer {TEST_DUAL_ROLE_TOKEN}"}


def _test_principal(principal_id: str, roles: str | list[str], token: str) -> dict[str, object]:
    return {
        "principal_id": principal_id,
        "category": "test",
        "roles": [roles] if isinstance(roles, str) else roles,
        "credentials": [{
            "key_id": f"{principal_id}-v1",
            "token_sha256": hashlib.sha256(token.encode()).hexdigest(),
        }],
    }


os.environ["API_AUTH_PRINCIPALS_JSON"] = json.dumps([
    _test_principal("pytest-operator", "operator", TEST_API_TOKEN),
    _test_principal("pytest-reviewer", "reviewer", TEST_REVIEWER_TOKEN),
    _test_principal("pytest-reader", "reader", TEST_READER_TOKEN),
    _test_principal("pytest-administrator", "administrator", TEST_ADMIN_TOKEN),
    _test_principal("pytest-dual-role", ["operator", "reviewer"], TEST_DUAL_ROLE_TOKEN),
])

from automotive_quality.api.main import app
from automotive_quality.api.rate_limits import Admission, get_rate_limiter


class _TestLease:
    renewal_failed = False

    def start(self) -> None:
        return None

    def release(self) -> None:
        return None


class _UnlimitedTestRateLimiter:
    def admit(self, principal_id, category) -> Admission:
        del principal_id, category
        return Admission(allowed=True, retry_after_seconds=1)

    def acquire_ai_lease(self, principal_id) -> _TestLease:
        del principal_id
        return _TestLease()


@pytest.fixture(autouse=True)
def offline_rate_limiter():
    previous = app.dependency_overrides.get(get_rate_limiter)
    app.dependency_overrides[get_rate_limiter] = _UnlimitedTestRateLimiter
    try:
        yield
    finally:
        if previous is None:
            app.dependency_overrides.pop(get_rate_limiter, None)
        else:
            app.dependency_overrides[get_rate_limiter] = previous
