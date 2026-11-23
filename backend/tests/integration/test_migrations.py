"""Migration checks on a fresh database: single head, up/down/up, no model drift."""

from collections.abc import Callable

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, pool, text

from app.models import Base
from tests.support.alembic import alembic_config


def test_migrations_round_trip_and_match_models(make_database: Callable[[], str]) -> None:
    url = make_database()
    cfg = alembic_config(url)
    script = ScriptDirectory.from_config(cfg)
    heads = script.get_heads()
    has_revisions = any(True for _ in script.walk_revisions())
    assert len(heads) == (1 if has_revisions else 0), f"expected a single head, got {heads}"

    engine = create_engine(url, poolclass=pool.NullPool)
    try:
        command.upgrade(cfg, "head")
        command.downgrade(cfg, "base")
        # A complete downgrade leaves nothing behind but Alembic's own table.
        with engine.connect() as conn:
            assert set(inspect(conn).get_table_names()) <= {"alembic_version"}
            user_enums = conn.execute(
                text(
                    "SELECT count(*) FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace "
                    "WHERE t.typtype = 'e' AND n.nspname = 'public'"
                )
            ).scalar_one()
            assert user_enums == 0
        command.upgrade(cfg, "head")

        with engine.connect() as conn:
            # Same comparison options as migrations/env.py.
            context = MigrationContext.configure(conn, opts={"compare_type": True})
            assert set(context.get_current_heads()) == set(heads)
            # Every model change needs a migration (AGENTS.md).
            assert compare_metadata(context, Base.metadata) == []
    finally:
        engine.dispose()
