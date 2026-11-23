"""FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import health
from app.core.config import Settings, get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging
from app.core.request_context import HEADER as REQUEST_ID_HEADER
from app.core.request_context import RequestContextMiddleware


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    include_traceback = settings.app_env == "development"  # ADR 0003
    configure_logging("api", settings.log_level, include_traceback=include_traceback)

    app = FastAPI(
        title="CampNet Data Workbench API",
        version="0.1.0",
        # Don't publish the interactive schema in production deployments.
        docs_url=None if settings.app_env == "production" else "/api/docs",
        openapi_url=None if settings.app_env == "production" else "/api/openapi.json",
    )
    app.add_middleware(RequestContextMiddleware, include_traceback=include_traceback)
    # CORS is added last = outermost, so even 500s sent by RequestContextMiddleware carry CORS
    # headers and browsers can read the body and X-Request-ID. Preflights skip request IDs.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=[REQUEST_ID_HEADER],
    )
    register_exception_handlers(app)
    app.include_router(health.router, prefix="/api/v1")
    return app


app = create_app()
