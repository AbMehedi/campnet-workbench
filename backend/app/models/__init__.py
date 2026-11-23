"""ORM models. Import each model module here so Alembic can discover it."""

from app.db.base import Base

__all__ = ["Base"]
