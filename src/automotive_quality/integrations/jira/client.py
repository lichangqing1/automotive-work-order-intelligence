from __future__ import annotations

import hashlib

import httpx


class JiraIssueTracker:
    name = "JIRA"

    def __init__(self, base_url: str, email: str, api_token: str, project_key: str, review_issue_type: str = "Task", bug_issue_type: str = "Bug") -> None:
        self.base_url = base_url.rstrip("/")
        self.project_key = project_key
        self.review_issue_type = review_issue_type
        self.bug_issue_type = bug_issue_type
        # Jira search is eventually consistent. Cache successful resolutions so
        # an immediate retry cannot create a duplicate before the label appears
        # in search. ExternalIssueLink remains the durable cross-process map.
        self._issue_keys_by_external_id: dict[str, str] = {}
        self.client = httpx.Client(auth=(email, api_token), headers={"Accept": "application/json", "Content-Type": "application/json"}, timeout=15)

    @staticmethod
    def _adf(text: str) -> dict:
        return {"type": "doc", "version": 1, "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}]}

    @staticmethod
    def _plain(value: object) -> str:
        if isinstance(value, str):
            return value
        if isinstance(value, dict):
            return " ".join(filter(None, (JiraIssueTracker._plain(item) for item in value.get("content", [])))) or str(value.get("text", ""))
        if isinstance(value, list):
            return " ".join(JiraIssueTracker._plain(item) for item in value)
        return ""

    def _create(self, summary: str, description: str, issue_type: str, external_id: str) -> str:
        cached_key = self._issue_keys_by_external_id.get(external_id)
        if cached_key is not None:
            return cached_key
        label = f"aqp-{hashlib.sha256(external_id.encode()).hexdigest()[:24]}"
        lookup = self.client.get(f"{self.base_url}/rest/api/3/search/jql", params={"jql": f'project = "{self.project_key}" AND labels = "{label}"', "fields": "key", "maxResults": 1})
        lookup.raise_for_status()
        issues = lookup.json().get("issues", [])
        if issues:
            issue_key = str(issues[0]["key"])
            self._issue_keys_by_external_id[external_id] = issue_key
            return issue_key
        response = self.client.post(f"{self.base_url}/rest/api/3/issue", json={"fields": {"project": {"key": self.project_key}, "summary": summary, "issuetype": {"name": issue_type}, "description": self._adf(description), "labels": [label]}})
        response.raise_for_status()
        issue_key = str(response.json()["key"])
        self._issue_keys_by_external_id[external_id] = issue_key
        return issue_key

    def get_issue(self, issue_key: str) -> dict[str, str]:
        response = self.client.get(f"{self.base_url}/rest/api/3/issue/{issue_key}")
        response.raise_for_status()
        fields = response.json()["fields"]
        return {"key": issue_key, "summary": fields["summary"], "description": self._plain(fields.get("description")), "status": fields["status"]["name"]}

    def create_review_issue(self, *, summary: str, description: str, external_id: str) -> str:
        return self._create(summary, f"{description}\nExternal ID: {external_id}", self.review_issue_type, external_id)

    def create_defect(self, *, summary: str, description: str, external_id: str) -> str:
        return self._create(summary, f"{description}\nExternal ID: {external_id}", self.bug_issue_type, external_id)

    def get_issue_status(self, issue_key: str) -> str:
        return self.get_issue(issue_key)["status"]

    def add_comment(self, issue_key: str, comment: str) -> None:
        response = self.client.post(f"{self.base_url}/rest/api/3/issue/{issue_key}/comment", json={"body": self._adf(comment)})
        response.raise_for_status()

    def transition_issue(self, issue_key: str, target_status: str) -> None:
        response = self.client.get(f"{self.base_url}/rest/api/3/issue/{issue_key}/transitions")
        response.raise_for_status()
        transition = next((item for item in response.json().get("transitions", []) if item["name"].casefold() == target_status.casefold() or item.get("to", {}).get("name", "").casefold() == target_status.casefold()), None)
        if transition is None:
            raise ValueError(f"No Jira transition to '{target_status}' for {issue_key}")
        changed = self.client.post(f"{self.base_url}/rest/api/3/issue/{issue_key}/transitions", json={"transition": {"id": transition["id"]}})
        changed.raise_for_status()

    def issue_url(self, issue_key: str) -> str:
        return f"{self.base_url}/browse/{issue_key}"
