from __future__ import annotations

import json
from urllib.error import HTTPError
from urllib.request import Request, urlopen


class ApiAuthenticationError(RuntimeError):
    """Raised without reflecting the configured service credential."""


def request_api(
    base_url: str,
    bearer_token: str | None,
    path: str,
    method: str = "GET",
    payload: dict[str, object] | None = None,
) -> object:
    if not bearer_token:
        raise ApiAuthenticationError("Dashboard API authentication is not configured")
    body = json.dumps(payload).encode() if payload is not None else None
    request = Request(
        f"{base_url.rstrip('/')}{path}",
        data=body,
        method=method,
        headers={"Authorization": f"Bearer {bearer_token}", "Content-Type": "application/json"},
    )
    try:
        with urlopen(request, timeout=15) as response:
            return json.loads(response.read())
    except HTTPError as exc:
        if exc.code == 401:
            raise ApiAuthenticationError("Dashboard API authentication was rejected") from None
        raise
