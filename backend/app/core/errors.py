"""Standard API error envelope (design §6.5).

Every error response has the shape
``{"error": {"code", "message", "details", "request_id"}}``. Messages for HTTP and internal
errors are fixed per code; exception text is never returned to clients.
"""

from enum import StrEnum
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import request_id_var


class ErrorCode(StrEnum):
    VALIDATION_ERROR = "VALIDATION_ERROR"
    BAD_REQUEST = "BAD_REQUEST"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    NOT_FOUND = "NOT_FOUND"
    METHOD_NOT_ALLOWED = "METHOD_NOT_ALLOWED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


MESSAGES: dict[ErrorCode, str] = {
    ErrorCode.VALIDATION_ERROR: "The request contains invalid fields.",
    ErrorCode.BAD_REQUEST: "The request could not be processed.",
    ErrorCode.UNAUTHORIZED: "Authentication is required.",
    ErrorCode.FORBIDDEN: "You do not have permission to perform this action.",
    ErrorCode.NOT_FOUND: "Resource not found.",
    ErrorCode.METHOD_NOT_ALLOWED: "Method not allowed.",
    ErrorCode.INTERNAL_ERROR: "An internal error occurred.",
}

_STATUS_CODES: dict[int, ErrorCode] = {
    HTTPStatus.BAD_REQUEST: ErrorCode.BAD_REQUEST,
    HTTPStatus.UNAUTHORIZED: ErrorCode.UNAUTHORIZED,
    HTTPStatus.FORBIDDEN: ErrorCode.FORBIDDEN,
    HTTPStatus.NOT_FOUND: ErrorCode.NOT_FOUND,
    HTTPStatus.METHOD_NOT_ALLOWED: ErrorCode.METHOD_NOT_ALLOWED,
    HTTPStatus.UNPROCESSABLE_CONTENT: ErrorCode.VALIDATION_ERROR,
}


class AppError(Exception):
    """Raised by services for expected failures with a stable, client-safe code and message."""

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        status_code: int = HTTPStatus.BAD_REQUEST,
        details: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or []


def code_for_status(status_code: int) -> ErrorCode:
    if status_code in _STATUS_CODES:
        return _STATUS_CODES[status_code]
    return ErrorCode.INTERNAL_ERROR if status_code >= 500 else ErrorCode.BAD_REQUEST


def error_body(
    code: ErrorCode, message: str, details: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    return {
        "error": {
            "code": code.value,
            "message": message,
            "details": details or [],
            "request_id": request_id_var.get(),
        }
    }


def error_response(
    status_code: int,
    code: ErrorCode,
    message: str | None = None,
    details: list[dict[str, Any]] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    # X-Request-ID is set by RequestContextMiddleware, not here.
    return JSONResponse(
        error_body(code, message or MESSAGES[code], details),
        status_code=status_code,
        headers=headers,
    )


def validation_details(exc: RequestValidationError) -> list[dict[str, Any]]:
    """Field-level details without echoing submitted values (pydantic `input`/`ctx`)."""
    details: list[dict[str, Any]] = []
    for err in exc.errors():
        loc = [str(part) for part in err.get("loc", ())]
        location = loc[0] if loc else None
        # Invalid JSON reports a character offset, not a field path.
        field = None if err.get("type") == "json_invalid" else (".".join(loc[1:]) or None)
        details.append({"location": location, "field": field, "reason": str(err.get("msg", ""))})
    return details


async def _http_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    return error_response(
        exc.status_code, code_for_status(exc.status_code), headers=dict(exc.headers or {})
    )


async def _validation_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    return error_response(
        HTTPStatus.UNPROCESSABLE_CONTENT,
        ErrorCode.VALIDATION_ERROR,
        details=validation_details(exc),
    )


async def _app_error_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AppError)
    return error_response(exc.status_code, exc.code, exc.message, exc.details)


async def _unhandled_handler(_: Request, __: Exception) -> JSONResponse:
    # Fallback only: RequestContextMiddleware normally catches and logs unhandled exceptions.
    return error_response(HTTPStatus.INTERNAL_SERVER_ERROR, ErrorCode.INTERNAL_ERROR)


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    app.add_exception_handler(RequestValidationError, _validation_handler)
    app.add_exception_handler(AppError, _app_error_handler)
    app.add_exception_handler(Exception, _unhandled_handler)
