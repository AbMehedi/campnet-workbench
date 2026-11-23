"""Shared FastAPI dependencies."""

from typing import Annotated

from fastapi import Depends, Request
from redis import Redis

from app.core.config import Settings
from app.db.redis import request_redis_client


def get_app_settings(request: Request) -> Settings:
    """Settings the running app was built with (see ``create_app``)."""
    settings: Settings = request.app.state.settings
    return settings


def get_redis(settings: Annotated[Settings, Depends(get_app_settings)]) -> Redis:
    """Redis client for the app's configured URL (request-path use only)."""
    return request_redis_client(settings.redis_url)
