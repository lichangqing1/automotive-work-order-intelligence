from __future__ import annotations

import hashlib
import json
import os

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
