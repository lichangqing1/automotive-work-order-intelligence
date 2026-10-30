from __future__ import annotations

import os

# A developer's .env may intentionally enable live Jira/OpenAI integrations.
# The default test suite must remain offline; opt-in integration tests construct
# their real clients directly from the dedicated environment variables.
os.environ["ISSUE_TRACKER"] = "local"
os.environ["LLM_PROVIDER"] = "mock"
