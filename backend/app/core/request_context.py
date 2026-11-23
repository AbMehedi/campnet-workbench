"""Request ID propagation, access logging and the unhandled-exception path.

Pure ASGI (not BaseHTTPMiddleware) so streaming responses keep working. It must sit outside
every user middleware except CORS (which wraps it so 500s get CORS headers). Starlette's
ServerErrorMiddleware sits outside all user middleware and re-raises, so this middleware
catches unhandled exceptions itself: otherwise a 500 would lose its request ID and uvicorn
would log the error a second time.

If an exception happens after the response has started, uvicorn additionally logs that the
response was incomplete (no exception text).
"""

import logging
import re
import time
import uuid
from http import HTTPStatus

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.errors import ErrorCode, error_response
from app.core.logging import request_id_var

HEADER = "X-Request-ID"
_VALID_REQUEST_ID = re.compile(r"[A-Za-z0-9._-]{1,128}")

access_logger = logging.getLogger("campnet.access")
error_logger = logging.getLogger("campnet.error")


def resolve_request_id(inbound: str | None) -> str:
    if inbound is not None and _VALID_REQUEST_ID.fullmatch(inbound):
        return inbound
    return str(uuid.uuid4())


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp, *, include_traceback: bool = False) -> None:
        self.app = app
        self.include_traceback = include_traceback

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        inbound = None
        for name, value in scope["headers"]:
            if name == b"x-request-id":
                inbound = value.decode("latin-1")
                break
        request_id = resolve_request_id(inbound)
        token = request_id_var.set(request_id)

        status_code = HTTPStatus.INTERNAL_SERVER_ERROR.value
        response_started = False
        start = time.perf_counter()

        async def send_with_request_id(message: Message) -> None:
            nonlocal status_code, response_started
            if message["type"] == "http.response.start":
                response_started = True
                status_code = message["status"]
                message.setdefault("headers", [])  # optional in the ASGI spec
                MutableHeaders(scope=message)[HEADER] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        except Exception as exc:
            status_code = HTTPStatus.INTERNAL_SERVER_ERROR.value
            # Never log str(exc): it may contain SQL, paths or post text.
            error_logger.error(
                "Unhandled exception",
                exc_info=exc if self.include_traceback else None,
                extra={"code": ErrorCode.INTERNAL_ERROR.value, "exc_type": type(exc).__name__},
            )
            if not response_started:
                response = error_response(status_code, ErrorCode.INTERNAL_ERROR)
                await response(scope, receive, send_with_request_id)
        finally:
            access_logger.info(
                "request",
                extra={
                    "method": scope.get("method"),
                    "path": scope.get("path"),  # query string deliberately omitted
                    "status": status_code,
                    "duration_ms": round((time.perf_counter() - start) * 1000, 2),
                },
            )
            request_id_var.reset(token)
