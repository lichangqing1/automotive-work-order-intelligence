from __future__ import annotations

from typing import Protocol


class IssueTracker(Protocol):
    name: str

    def get_issue(self, issue_key: str) -> dict[str, str]: ...
    def create_review_issue(self, *, summary: str, description: str, external_id: str) -> str: ...
    def get_issue_status(self, issue_key: str) -> str: ...
    def create_defect(self, *, summary: str, description: str, external_id: str) -> str: ...
    def add_comment(self, issue_key: str, comment: str) -> None: ...
    def issue_url(self, issue_key: str) -> str | None: ...


class LocalIssueTracker:
    name = "LOCAL"

    def __init__(self) -> None:
        self.issues: dict[str, dict[str, object]] = {}
        self.external_ids: dict[str, str] = {}
        self._counter = 0

    def get_issue(self, issue_key: str) -> dict[str, str]:
        issue = self.issues.get(issue_key)
        if issue is None:
            issue = {"summary": f"Local requirement {issue_key}", "description": f"Acceptance criteria for {issue_key}", "status": "To Do", "comments": []}
            self.issues[issue_key] = issue
        return {"key": issue_key, "summary": str(issue["summary"]), "description": str(issue["description"]), "status": str(issue["status"])}

    def _create(self, prefix: str, summary: str, description: str, external_id: str) -> str:
        if external_id in self.external_ids:
            return self.external_ids[external_id]
        self._counter += 1
        key = f"{prefix}-{self._counter}"
        self.issues[key] = {"summary": summary, "description": description, "status": "To Do", "comments": []}
        self.external_ids[external_id] = key
        return key

    def create_review_issue(self, *, summary: str, description: str, external_id: str) -> str:
        return self._create("REVIEW", summary, f"{description}\nExternal ID: {external_id}", external_id)

    def create_defect(self, *, summary: str, description: str, external_id: str) -> str:
        return self._create("BUG", summary, f"{description}\nExternal ID: {external_id}", external_id)

    def get_issue_status(self, issue_key: str) -> str:
        return str(self.issues[issue_key]["status"])

    def set_issue_status(self, issue_key: str, status: str) -> None:
        self.issues[issue_key]["status"] = status

    def add_comment(self, issue_key: str, comment: str) -> None:
        comments = self.issues[issue_key]["comments"]
        assert isinstance(comments, list)
        comments.append(comment)

    def issue_url(self, issue_key: str) -> str:
        return f"local://issues/{issue_key}"
