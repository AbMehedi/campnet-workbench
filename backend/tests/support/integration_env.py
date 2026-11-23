"""Integration-test environment loading and safety guards.

Pure functions (no I/O) so they can be unit-tested without Postgres or Redis. Lives outside
tests/integration/ so its unit tests aren't auto-marked as integration tests.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass

from redis import Redis
from sqlalchemy.engine import make_url

TEST_DB_NAME = re.compile(r"campnet_test_[0-9a-f]{12}")
MAINTENANCE_DBS = frozenset({"postgres", "template1"})

REQUIRE_FLAG = "CAMPNET_REQUIRE_INTEGRATION"


class IntegrationConfigError(RuntimeError):
    """Configuration is unsafe or (when required) missing. Always fails the run."""


@dataclass(frozen=True)
class IntegrationEnv:
    admin_database_url: str
    redis_url: str


def integration_required(environ: Mapping[str, str]) -> bool:
    return environ.get(REQUIRE_FLAG, "") not in ("", "0", "false", "False")


def load_integration_env(environ: Mapping[str, str]) -> IntegrationEnv | str:
    """Return the env, or a skip reason (str) when services aren't configured.

    Raises IntegrationConfigError instead of returning a skip reason when
    CAMPNET_REQUIRE_INTEGRATION is set, and always for unsafe configuration.
    """
    admin_url = environ.get("TEST_DATABASE_URL", "")
    redis_url = environ.get("TEST_REDIS_URL", "")
    missing = [
        name
        for name, v in (("TEST_DATABASE_URL", admin_url), ("TEST_REDIS_URL", redis_url))
        if not v
    ]
    if missing:
        reason = f"integration services not configured: {', '.join(missing)} unset"
        if integration_required(environ):
            raise IntegrationConfigError(reason)
        return reason
    check_admin_url(admin_url, environ.get("DATABASE_URL"))
    check_redis_url(redis_url, environ.get("REDIS_URL"))
    return IntegrationEnv(admin_database_url=admin_url, redis_url=redis_url)


def _redis_target(url: str) -> tuple[object, object, int]:
    kwargs = Redis.from_url(url).connection_pool.connection_kwargs
    return (kwargs.get("host") or kwargs.get("path"), kwargs.get("port"), int(kwargs.get("db", 0)))


def check_redis_url(test_url: str, app_url: str | None) -> None:
    target = _redis_target(test_url)
    if target[2] == 0:
        raise IntegrationConfigError("TEST_REDIS_URL must not use Redis DB 0 (used by the app)")
    if app_url and _redis_target(app_url) == target:
        raise IntegrationConfigError("TEST_REDIS_URL must differ from REDIS_URL")


def check_admin_url(test_url: str, app_url: str | None) -> None:
    """Sanity check only; real protection is that tests only create/drop generated names."""
    test = make_url(test_url)
    if test.database not in MAINTENANCE_DBS:
        raise IntegrationConfigError("TEST_DATABASE_URL must point at a maintenance DB (postgres)")
    if app_url:
        app = make_url(app_url)
        if (app.host, app.port, app.database) == (test.host, test.port, test.database):
            raise IntegrationConfigError("TEST_DATABASE_URL must differ from DATABASE_URL")


def is_test_database_url(url: str) -> bool:
    name = make_url(url).database
    return name is not None and TEST_DB_NAME.fullmatch(name) is not None
