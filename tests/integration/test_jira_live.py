import os
from uuid import uuid4

import pytest

from automotive_quality.integrations.jira import JiraIssueTracker


@pytest.mark.jira_integration
def test_live_jira_create_retrieve_and_comment() -> None:
    required = ["JIRA_BASE_URL", "JIRA_EMAIL", "JIRA_API_TOKEN", "JIRA_PROJECT_KEY", "JIRA_REQUIREMENT_KEY", "JIRA_APPROVAL_TRANSITION_NAME"]
    if not all(os.getenv(name) for name in required):
        pytest.skip("Live Jira credentials are not configured")
    tracker = JiraIssueTracker(
        os.environ["JIRA_BASE_URL"], os.environ["JIRA_EMAIL"], os.environ["JIRA_API_TOKEN"], os.environ["JIRA_PROJECT_KEY"],
    )
    requirement = tracker.get_issue(os.environ["JIRA_REQUIREMENT_KEY"])
    assert requirement["summary"] and requirement["description"]
    external_id = f"LIVE-{uuid4().hex[:8]}"
    review_key = tracker.create_review_issue(summary=f"AI test review contract {external_id}", description=f"Requirement: {requirement['key']}", external_id=f"review:{external_id}")
    assert tracker.create_review_issue(summary="idempotent retry", description="retry", external_id=f"review:{external_id}") == review_key
    tracker.transition_issue(review_key, os.environ["JIRA_APPROVAL_TRANSITION_NAME"])
    assert tracker.get_issue_status(review_key).casefold() in {value.strip().casefold() for value in os.getenv("JIRA_APPROVED_STATUSES", "Approved,Done").split(",")}
    bug_key = tracker.create_defect(summary=f"Automated failure contract {external_id}", description="Expected: pass\nActual: fail", external_id=f"defect:{external_id}")
    tracker.add_comment(bug_key, "AI-assisted RCA\nEvidence: deterministic live integration failure fixture.\nRecommended check: inspect test environment.")
    assert tracker.get_issue(bug_key)["key"] == bug_key
