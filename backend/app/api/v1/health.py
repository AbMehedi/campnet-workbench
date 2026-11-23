"""Liveness and readiness checks (§14.2). Never return config, credentials or paths here."""

from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from redis import Redis
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.deps import get_redis
from app.db.session import get_db

router = APIRouter(tags=["health"])


@router.get("/health/live")
def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready")
def ready(
    response: Response,
    db: Annotated[Session, Depends(get_db)],
    redis: Annotated[Redis, Depends(get_redis)],
) -> dict[str, object]:
    checks: dict[str, str] = {}

    try:
        db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "unavailable"

    try:
        redis.ping()
        checks["queue"] = "ok"
    except Exception:
        checks["queue"] = "unavailable"

    healthy = all(v == "ok" for v in checks.values())
    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "ok" if healthy else "degraded", "checks": checks}
