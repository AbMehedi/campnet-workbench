"""Application configuration, loaded from environment variables (see .env.example)."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Default to the safest mode; local setups opt into development via .env (ADR 0003).
    app_env: Literal["development", "test", "production"] = "production"
    app_secret_key: SecretStr = SecretStr("change-me")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    database_url: str = "postgresql+psycopg://campnet:campnet@localhost:5432/campnet"
    redis_url: str = "redis://localhost:6379/0"

    storage_backend: Literal["local", "s3-compatible"] = "local"
    local_media_root: Path = Path("./var/media")
    s3_endpoint_url: str | None = None
    s3_bucket: str | None = None
    s3_access_key_id: SecretStr | None = None
    s3_secret_access_key: SecretStr | None = None

    ocr_default_adapter: str = "tesseract"
    max_upload_bytes: int = 50 * 1024 * 1024

    allowed_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])


@lru_cache
def get_settings() -> Settings:
    return Settings()
