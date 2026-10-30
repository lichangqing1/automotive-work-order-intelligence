from __future__ import annotations

import httpx

from automotive_quality.integrations.jira import JiraIssueTracker


def test_create_review_issue_is_idempotent_while_jira_search_is_stale() -> None:
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "GET":
            return httpx.Response(200, json={"issues": []})
        return httpx.Response(201, json={"key": "QA-5"})

    tracker = JiraIssueTracker("https://example.atlassian.net", "user@example.com", "token", "QA")
    tracker.client.close()
    tracker.client = httpx.Client(transport=httpx.MockTransport(handle))

    first = tracker.create_review_issue(summary="Review", description="First attempt", external_id="review:123")
    second = tracker.create_review_issue(summary="Retry", description="Retry attempt", external_id="review:123")

    assert first == second == "QA-5"
    assert [request.method for request in requests] == ["GET", "POST"]


def test_create_uses_existing_jira_issue_found_by_idempotency_label() -> None:
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"issues": [{"key": "QA-4"}]})

    tracker = JiraIssueTracker("https://example.atlassian.net", "user@example.com", "token", "QA")
    tracker.client.close()
    tracker.client = httpx.Client(transport=httpx.MockTransport(handle))

    assert tracker.create_defect(summary="Failure", description="Evidence", external_id="defect:123") == "QA-4"
    assert tracker.create_defect(summary="Retry", description="Retry", external_id="defect:123") == "QA-4"
    assert len(requests) == 1
