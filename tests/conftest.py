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
TEST_API_TOKEN = "test-only-bearer-token-with-no-production-value"
TEST_AUTH_HEADERS = {"Authorization": f"Bearer {TEST_API_TOKEN}"}
os.environ["API_AUTH_PRINCIPALS_JSON"] = json.dumps([{
    "principal_id": "pytest-client",
    "category": "test",
    "roles": ["operator", "reviewer"],
    "credentials": [{
        "key_id": "pytest-v1",
        "token_sha256": hashlib.sha256(TEST_API_TOKEN.encode()).hexdigest(),
    }],
}])
