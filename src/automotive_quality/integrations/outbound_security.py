from __future__ import annotations

import re
from dataclasses import dataclass

MAX_JIRA_SUMMARY = 255
MAX_JIRA_DESCRIPTION = 8_000
MAX_JIRA_COMMENT = 8_000
MAX_EXTERNAL_ID = 256

_SECRET_PATTERNS = (
    re.compile(r"(?i)\b(bearer\s+)[A-Za-z0-9._~+/=-]{8,}"),
    re.compile(r"(?i)\b(api[_-]?key|token|password|secret)\s*[:=]\s*[^\s,;]+"),
    re.compile(r"(?i)(https?://[^:/\s]+:)[^@/\s]+@"),
)
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class OutboundPayloadRejected(ValueError):
    pass


@dataclass(frozen=True)
class JiraPayload:
    summary: str
    description: str
    external_id: str


def sanitize_text(value: str, *, field: str, max_length: int) -> str:
    cleaned = _CONTROL.sub("", value)
    for pattern in _SECRET_PATTERNS:
        cleaned = pattern.sub(lambda match: f"{match.group(1) if match.lastindex else ''}[REDACTED]", cleaned)
    if len(cleaned) > max_length:
        raise OutboundPayloadRejected(f"{field} exceeds the outbound limit")
    return cleaned


def jira_payload(summary: str, description: str, external_id: str) -> JiraPayload:
    if not external_id or len(external_id) > MAX_EXTERNAL_ID or not re.fullmatch(r"[A-Za-z0-9._:-]+", external_id):
        raise OutboundPayloadRejected("external_id is invalid")
    return JiraPayload(
        summary=sanitize_text(summary, field="summary", max_length=MAX_JIRA_SUMMARY),
        description=sanitize_text(description, field="description", max_length=MAX_JIRA_DESCRIPTION),
        external_id=external_id,
    )


def jira_comment(comment: str) -> str:
    return sanitize_text(comment, field="comment", max_length=MAX_JIRA_COMMENT)


def safe_external_error(exc: Exception) -> str:
    name = type(exc).__name__.lower()
    if "timeout" in name:
        category = "EXTERNAL_TIMEOUT"
    elif "connect" in name or "network" in name:
        category = "EXTERNAL_CONNECTION"
    elif "auth" in name or "permission" in name:
        category = "EXTERNAL_AUTHENTICATION"
    elif "payload" in name or "validation" in name:
        category = "EXTERNAL_PAYLOAD_REJECTED"
    else:
        category = "EXTERNAL_FAILURE"
    return f"{category}: external synchronization failed"
