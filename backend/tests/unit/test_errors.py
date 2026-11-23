import json
import logging
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.core.config import Settings
from app.core.errors import AppError, ErrorCode
from app.core.logging import JsonFormatter
from app.main import create_app

MARKER = "সংবেদনশীল-secret-value"


class Item(BaseModel):
    name: str
    count: int


class Batch(BaseModel):
    items: list[Item]


def _build(app_env: str = "test") -> FastAPI:
    app = create_app(Settings(app_env=app_env))  # type: ignore[arg-type]

    @app.post("/test/items")
    def create_items(batch: Batch) -> dict[str, int]:
        return {"n": len(batch.items)}

    @app.get("/test/app-error")
    def app_error() -> None:
        raise AppError(
            ErrorCode.FORBIDDEN,
            "Not a member of this project.",
            status_code=403,
            details=[{"reason": "membership"}],
        )

    @app.get("/test/boom")
    def boom() -> None:
        raise RuntimeError(f"postgresql://user:pw@db {MARKER}")

    @app.get("/test/bad-response", response_model=Item)
    def bad_response() -> dict[str, str]:
        return {"name": MARKER, "count": "not-a-number"}

    return app


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(_build(), raise_server_exceptions=False) as c:
        yield c


def _formatted(caplog: pytest.LogCaptureFixture, *, include_traceback: bool = False) -> str:
    # Server-side logs only; the test client's own httpx logs are not the app's.
    formatter = JsonFormatter("api", include_traceback=include_traceback)
    return "\n".join(formatter.format(r) for r in caplog.records if r.name.startswith("campnet"))


def _assert_envelope(body: dict[str, object], code: str, request_id: str) -> dict[str, object]:
    assert set(body) == {"error"}
    error = body["error"]
    assert isinstance(error, dict)
    assert set(error) == {"code", "message", "details", "request_id"}
    assert error["code"] == code
    assert isinstance(error["details"], list)
    assert error["request_id"] == request_id
    return error


# --- request IDs -----------------------------------------------------------------------------


def test_request_id_generated_when_absent(client: TestClient) -> None:
    resp = client.get("/api/v1/health/live")
    assert len(resp.headers["x-request-id"]) == 36
    assert resp.headers.get_list("x-request-id") == [resp.headers["x-request-id"]]


def test_valid_inbound_request_id_is_echoed(client: TestClient) -> None:
    resp = client.get("/api/v1/health/live", headers={"X-Request-ID": "proxy-abc.123_X"})
    assert resp.headers["x-request-id"] == "proxy-abc.123_X"


@pytest.mark.parametrize("bad", ["a" * 129, "has space", "abc\n", "abc\r\nX-Evil: 1", "ü", ""])
def test_invalid_inbound_request_id_is_replaced(bad: str) -> None:
    from app.core.request_context import resolve_request_id

    assert resolve_request_id(bad) != bad
    assert len(resolve_request_id(bad)) == 36


def test_same_request_id_in_header_body_and_logs(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    resp = client.get("/nope", headers={"X-Request-ID": "corr-1"})
    _assert_envelope(resp.json(), "NOT_FOUND", "corr-1")
    assert resp.headers["x-request-id"] == "corr-1"
    access = [json.loads(line) for line in _formatted(caplog).splitlines()]
    assert any(e["logger"] == "campnet.access" and e["request_id"] == "corr-1" for e in access)


# --- access log ------------------------------------------------------------------------------


def test_access_log_one_line_without_query_string(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    client.get("/api/v1/health/live?q=secret-search-term")
    access = [r for r in caplog.records if r.name == "campnet.access"]
    assert len(access) == 1
    entry = json.loads(JsonFormatter("api").format(access[0]))
    assert entry["method"] == "GET"
    assert entry["path"] == "/api/v1/health/live"
    assert entry["status"] == 200
    assert isinstance(entry["duration_ms"], float)
    assert "secret-search-term" not in _formatted(caplog)


# --- envelope --------------------------------------------------------------------------------


def test_not_found(client: TestClient) -> None:
    resp = client.get("/does-not-exist", headers={"X-Request-ID": "r"})
    assert resp.status_code == 404
    error = _assert_envelope(resp.json(), "NOT_FOUND", "r")
    assert error["details"] == []


def test_method_not_allowed_keeps_allow_header(client: TestClient) -> None:
    resp = client.delete("/api/v1/health/live", headers={"X-Request-ID": "r"})
    assert resp.status_code == 405
    _assert_envelope(resp.json(), "METHOD_NOT_ALLOWED", "r")
    assert "GET" in resp.headers["allow"]


def test_validation_error_has_field_details_without_input(client: TestClient) -> None:
    resp = client.post(
        "/test/items",
        json={"items": [{"name": "ok", "count": 1}, {"name": MARKER, "count": MARKER}]},
        headers={"X-Request-ID": "r"},
    )
    assert resp.status_code == 422
    error = _assert_envelope(resp.json(), "VALIDATION_ERROR", "r")
    assert error["details"] == [
        {
            "location": "body",
            "field": "items.1.count",
            "reason": error["details"][0]["reason"],  # type: ignore[index]
        }
    ]
    assert MARKER not in resp.text


def test_body_level_validation_error_has_null_field(client: TestClient) -> None:
    resp = client.post(
        "/test/items", content=b"not json", headers={"content-type": "application/json"}
    )
    assert resp.status_code == 422
    details = resp.json()["error"]["details"]
    assert details and details[0]["location"] == "body"
    assert details[0]["field"] is None


def test_missing_body_reports_null_field(client: TestClient) -> None:
    resp = client.post("/test/items")
    assert resp.status_code == 422
    assert resp.json()["error"]["details"][0] == {
        "location": "body",
        "field": None,
        "reason": resp.json()["error"]["details"][0]["reason"],
    }


def test_app_error_passthrough(client: TestClient) -> None:
    resp = client.get("/test/app-error", headers={"X-Request-ID": "r"})
    assert resp.status_code == 403
    error = _assert_envelope(resp.json(), "FORBIDDEN", "r")
    assert error["message"] == "Not a member of this project."
    assert error["details"] == [{"reason": "membership"}]


@pytest.mark.parametrize("path", ["/test/boom", "/test/bad-response"])
def test_unhandled_exception_is_generic_500_logged_once(
    client: TestClient, caplog: pytest.LogCaptureFixture, path: str
) -> None:
    caplog.set_level(logging.INFO)
    resp = client.get(path, headers={"X-Request-ID": "r500"})
    assert resp.status_code == 500
    assert resp.headers["x-request-id"] == "r500"
    error = _assert_envelope(resp.json(), "INTERNAL_ERROR", "r500")
    assert error["message"] == "An internal error occurred."
    for leaked in (MARKER, "postgresql", "RuntimeError", "ResponseValidationError"):
        assert leaked not in resp.text

    errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert len(errors) == 1
    assert errors[0].__dict__["code"] == "INTERNAL_ERROR"
    logs = _formatted(caplog)
    assert MARKER not in logs
    assert "postgresql" not in logs
    access = [r for r in caplog.records if r.name == "campnet.access"]
    assert [r.__dict__["status"] for r in access] == [500]


def test_traceback_logged_only_in_development(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO)
    with TestClient(_build("development"), raise_server_exceptions=False) as dev:
        dev.get("/test/boom")
    [record] = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert record.exc_info is not None
    caplog.clear()
    with TestClient(_build("production"), raise_server_exceptions=False) as prod:
        prod.get("/test/boom")
    [record] = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert record.exc_info is None


def test_cors_exposes_request_id_header() -> None:
    app = create_app(Settings(app_env="test", allowed_origins=["http://localhost:5173"]))
    resp = TestClient(app).get("/api/v1/health/live", headers={"Origin": "http://localhost:5173"})
    assert "x-request-id" in resp.headers["access-control-expose-headers"].lower()


def test_cross_origin_500_carries_cors_and_request_id() -> None:
    app = _build()
    with TestClient(app, raise_server_exceptions=False) as c:
        resp = c.get("/test/boom", headers={"Origin": "http://localhost:5173"})
    assert resp.status_code == 500
    assert resp.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "x-request-id" in resp.headers["access-control-expose-headers"].lower()
    assert resp.headers["x-request-id"]
