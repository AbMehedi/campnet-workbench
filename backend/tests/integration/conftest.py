"""Integration-test fixtures: throwaway PostgreSQL database + isolated Redis DB.

See README.md in this directory for how to run these tests and the required env vars.
"""

import os
import uuid
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from alembic import command
from fastapi.testclient import TestClient
from redis import Redis
from sqlalchemy import Engine, create_engine, pool, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_db, get_engine, get_sessionmaker
from app.main import create_app
from tests.support.alembic import alembic_config
from tests.support.integration_env import (
    TEST_DB_NAME,
    IntegrationConfigError,
    IntegrationEnv,
    integration_required,
    is_test_database_url,
    load_integration_env,
)

INTEGRATION_DIR = Path(__file__).parent


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    # This hook sees every collected item in the session: only tag tests in this directory.
    for item in items:
        if INTEGRATION_DIR in item.path.parents:
            item.add_marker(pytest.mark.integration)


def _clear_app_caches() -> None:
    get_settings.cache_clear()
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()


@pytest.fixture(scope="session")
def integration_env() -> IntegrationEnv:
    result = load_integration_env(os.environ)
    if isinstance(result, str):
        pytest.skip(result)
    engine = create_engine(
        result.admin_database_url, poolclass=pool.NullPool, connect_args={"connect_timeout": 2}
    )
    probe = Redis.from_url(result.redis_url, socket_connect_timeout=2, socket_timeout=2)
    try:
        with engine.connect():
            pass
        probe.ping()
    except Exception as exc:
        # Type only: messages can contain connection strings.
        reason = f"integration services unreachable ({type(exc).__name__})"
        if integration_required(os.environ):
            pytest.fail(reason)
        pytest.skip(reason)
    finally:
        engine.dispose()
        probe.close()
    return result


@pytest.fixture(scope="session")
def make_database(integration_env: IntegrationEnv) -> Iterator[Callable[[], str]]:
    """Factory creating empty UTF-8 databases named campnet_test_<hex>; all dropped at the end."""
    admin_url = make_url(integration_env.admin_database_url)
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT", poolclass=pool.NullPool)
    created: list[str] = []

    def _make() -> str:
        name = f"campnet_test_{uuid.uuid4().hex[:12]}"
        with admin.connect() as conn:
            conn.execute(text(f"CREATE DATABASE \"{name}\" TEMPLATE template0 ENCODING 'UTF8'"))
        created.append(name)
        return admin_url.set(database=name).render_as_string(hide_password=False)

    yield _make

    with admin.connect() as conn:
        for name in created:
            if not TEST_DB_NAME.fullmatch(name):  # never drop anything we didn't generate
                raise IntegrationConfigError("refusing to drop a non-test database")
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
    admin.dispose()


# Package scope: the env/cache switch is undone before tests outside tests/integration run, so a
# unit test that forgets to override get_db can't silently hit a real database.
@pytest.fixture(scope="package", autouse=True)
def test_settings(
    integration_env: IntegrationEnv, make_database: Callable[[], str]
) -> Iterator[Settings]:
    """Migrated throwaway DB; the app's own settings/engine caches point at it all session."""
    database_url = make_database()
    command.upgrade(alembic_config(database_url), "head")

    patch = pytest.MonkeyPatch()
    patch.setenv("APP_ENV", "test")
    patch.setenv("DATABASE_URL", database_url)
    patch.setenv("REDIS_URL", integration_env.redis_url)
    _clear_app_caches()
    try:
        settings = get_settings()
        if not is_test_database_url(settings.database_url):
            raise IntegrationConfigError("app settings do not point at a test database")
        yield settings
    finally:
        get_engine().dispose()
        patch.undo()
        _clear_app_caches()


@pytest.fixture(scope="package")
def db_engine(test_settings: Settings) -> Engine:
    return get_engine()


@pytest.fixture
def db_session(db_engine: Engine) -> Iterator[Session]:
    """Session inside an outer transaction that is always rolled back.

    Code under test may commit: with create_savepoint, commits only release savepoints.
    """
    with db_engine.connect() as connection:
        outer = connection.begin()
        session = Session(bind=connection, join_transaction_mode="create_savepoint")
        try:
            yield session
        finally:
            session.close()
            outer.rollback()


@pytest.fixture
def redis_client(test_settings: Settings) -> Iterator[Redis]:
    client = Redis.from_url(test_settings.redis_url, socket_connect_timeout=2, socket_timeout=2)
    client.flushdb()
    try:
        yield client
    finally:
        client.flushdb()
        client.close()


@pytest.fixture
def api_client(
    test_settings: Settings, db_session: Session, redis_client: Redis
) -> Iterator[TestClient]:
    """API client on the test DB session and test Redis.

    All requests share db_session's single connection: never use this client concurrently.
    """
    app = create_app(test_settings)

    def _db() -> Iterator[Session]:
        yield db_session

    app.dependency_overrides[get_db] = _db
    with TestClient(app) as client:
        yield client
