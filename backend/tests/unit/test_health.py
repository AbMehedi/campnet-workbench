from collections.abc import Iterator

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.main import app


def test_liveness() -> None:
    client = TestClient(app)
    resp = client.get("/api/v1/health/live")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_readiness_reports_unavailable_dependencies_without_leaking_details() -> None:
    class BrokenSession:
        def execute(self, *_: object) -> None:
            raise RuntimeError("postgresql://user:secret@host/db refused")

    def broken_db() -> Iterator[Session]:
        yield BrokenSession()  # type: ignore[misc]

    app.dependency_overrides[get_db] = broken_db
    try:
        resp = TestClient(app).get("/api/v1/health/ready")
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 503
    assert resp.json()["checks"]["database"] == "unavailable"
    assert "secret" not in resp.text
