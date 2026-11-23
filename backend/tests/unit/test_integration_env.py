"""Integration-harness guards and marker scoping; no services needed."""

import subprocess
import sys
from pathlib import Path

import pytest

from tests.support.integration_env import (
    IntegrationConfigError,
    IntegrationEnv,
    check_admin_url,
    check_redis_url,
    is_test_database_url,
    load_integration_env,
)

BACKEND_DIR = Path(__file__).parents[2]
ADMIN = "postgresql+psycopg://u:p@localhost:5432/postgres"
REDIS = "redis://localhost:6379/15"


def test_missing_env_skips_by_default() -> None:
    result = load_integration_env({})
    assert isinstance(result, str)
    assert "TEST_DATABASE_URL" in result


def test_missing_env_fails_when_required() -> None:
    with pytest.raises(IntegrationConfigError):
        load_integration_env({"CAMPNET_REQUIRE_INTEGRATION": "1"})


def test_valid_env_loads() -> None:
    env = {"TEST_DATABASE_URL": ADMIN, "TEST_REDIS_URL": REDIS, "REDIS_URL": "redis://x:6379/0"}
    assert load_integration_env(env) == IntegrationEnv(ADMIN, REDIS)


@pytest.mark.parametrize(
    "url", ["redis://localhost:6379/0", "redis://localhost:6379", "redis://localhost:6379?db=0"]
)
def test_redis_db_zero_refused(url: str) -> None:
    with pytest.raises(IntegrationConfigError):
        check_redis_url(url, None)


def test_redis_same_as_app_refused() -> None:
    with pytest.raises(IntegrationConfigError):
        check_redis_url(REDIS, "redis://localhost:6379/15")
    check_redis_url(REDIS, "redis://localhost:6379/0")


def test_admin_url_must_be_maintenance_db_and_differ_from_app() -> None:
    with pytest.raises(IntegrationConfigError):
        check_admin_url("postgresql+psycopg://u:p@localhost:5432/campnet", None)
    with pytest.raises(IntegrationConfigError):
        check_admin_url(ADMIN, ADMIN)
    check_admin_url(ADMIN, "postgresql+psycopg://u:p@localhost:5432/campnet")


@pytest.mark.parametrize(
    ("name", "ok"),
    [
        ("campnet_test_0123456789ab", True),
        ("campnet", False),
        ("campnet_test_0123456789ab_x", False),
        ("campnet_test_XYZ", False),
    ],
)
def test_test_database_name_matching(name: str, ok: bool) -> None:
    assert is_test_database_url(f"postgresql+psycopg://u:p@h/{name}") is ok


def _collect(marker: str) -> str:
    result = subprocess.run(  # noqa: S603 - fixed args, test-only
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-m", marker],
        cwd=BACKEND_DIR,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout[-2000:]
    return result.stdout


def test_integration_marker_applies_only_to_integration_directory() -> None:
    unit = _collect("not integration")
    assert "tests/unit/test_health.py" in unit
    assert "tests/integration/" not in unit
    integration = _collect("integration")
    assert "tests/integration/test_harness.py" in integration
    assert "tests/unit/" not in integration
