from __future__ import annotations

import logging
from hashlib import sha256

LOGGER = logging.getLogger("automotive_quality.security")


def principal_digest(principal_id: str | None) -> str | None:
    return sha256(principal_id.encode()).hexdigest()[:16] if principal_id else None


def log_security_event(event: str, *, principal_id: str | None = None, **fields: object) -> None:
    LOGGER.warning(
        "security_event=%s",
        event,
        extra={
            "security_event": event,
            "principal_digest": principal_digest(principal_id),
            **fields,
        },
    )
