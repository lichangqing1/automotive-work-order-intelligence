from __future__ import annotations

from starlette.types import ASGIApp, Message, Receive, Scope, Send


class RequestBodyLimitMiddleware:
    """Bounded ASGI body gate that runs before framework body parsing."""

    def __init__(self, app: ASGIApp, *, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        raw_length = headers.get(b"content-length")
        if raw_length is not None:
            try:
                declared = int(raw_length)
            except ValueError:
                await self._reject(send, 400, "Invalid Content-Length")
                return
            if declared < 0:
                await self._reject(send, 400, "Invalid Content-Length")
                return
            if declared > self.max_bytes:
                await self._reject(send, 413, "Request body exceeds the configured limit")
                return

        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            if message["type"] != "http.request":
                await self._reject(send, 400, "Invalid request body event")
                return
            chunk = message.get("body", b"")
            remaining = self.max_bytes - len(body)
            body.extend(chunk[: remaining + 1])
            if len(body) > self.max_bytes:
                await self._reject(send, 413, "Request body exceeds the configured limit")
                return
            if not message.get("more_body", False):
                break

        replayed = False

        async def limited_receive() -> Message:
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return {"type": "http.disconnect"}

        await self.app(scope, limited_receive, send)

    @staticmethod
    async def _reject(send: Send, status_code: int, detail: str) -> None:
        body = ('{"detail":"' + detail + '"}').encode()
        await send({
            "type": "http.response.start",
            "status": status_code,
            "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(body)).encode())],
        })
        await send({"type": "http.response.body", "body": body})
