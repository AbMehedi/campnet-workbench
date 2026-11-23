"""Programmatic Alembic configuration for tests."""

from pathlib import Path

from alembic.config import Config

BACKEND_DIR = Path(__file__).parents[2]


def alembic_config(database_url: str) -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.attributes["database_url"] = database_url
    cfg.attributes["configure_logger"] = False  # don't let Alembic reset app logging
    return cfg
