"""One ``http_request`` log line per request to a ticket route, bound to the ticket.

Replaces uvicorn's access log (run uvicorn with ``--no-access-log``). The ticket ID comes from
the path (``/tickets/{ticket_id}[/approval]``) or, for ``POST /tickets``, from the JSON body.
It is bound for the whole request, so every line the API logs while handling it carries
``ticket_id`` and ``workflow_id``.
"""

from __future__ import annotations

import json
import logging
import re
import time

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.domain.models import TICKET_ID_PATTERN
from app.logging import bind_ticket

log = logging.getLogger("app.api")

_TICKET_ID = re.compile(TICKET_ID_PATTERN)
_TICKET_PATH = re.compile(r"^/tickets/([^/]+)(?:/approval)?/?$")
_MAX_BODY_BYTES = 64 * 1024


def ticket_id_from(method: str, path: str, body: bytes) -> str | None:
    """The ticket a request is about, if it names a valid ticket ID."""
    match = _TICKET_PATH.match(path)
    if match:
        candidate = match.group(1)
    elif method == "POST" and path.rstrip("/") == "/tickets":
        try:
            candidate = json.loads(body).get("ticket_id")
        except (ValueError, AttributeError):
            return None
    else:
        return None
    if isinstance(candidate, str) and _TICKET_ID.fullmatch(candidate):
        return candidate
    return None


class TicketRequestLog:
    """Pure ASGI middleware; the body is read once and replayed to the app."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "")
        if scope["type"] != "http" or not (path == "/tickets" or path.startswith("/tickets/")):
            await self.app(scope, receive, send)
            return

        started = time.perf_counter()
        method = scope["method"]
        body, receive = await _buffer_body(receive) if method == "POST" else (b"", receive)
        ticket_id = ticket_id_from(method, path, body)
        status_code = 500

        async def send_with_status(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        with bind_ticket(ticket_id):
            try:
                await self.app(scope, receive, send_with_status)
            finally:
                log.info(
                    "http_request",
                    extra={
                        "method": method,
                        "path": path,
                        "status": status_code,
                        "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                    },
                )


async def _buffer_body(receive: Receive) -> tuple[bytes, Receive]:
    """Read the request body and return a ``receive`` that replays it."""
    messages: list[Message] = []
    body = b""
    while True:
        message = await receive()
        messages.append(message)
        if message["type"] != "http.request":
            break
        if len(body) < _MAX_BODY_BYTES:
            body += message.get("body", b"")
        if not message.get("more_body", False):
            break

    async def replay() -> Message:
        return messages.pop(0) if messages else await receive()

    return body[:_MAX_BODY_BYTES], replay
