"""Integration tests for the harness itself (and the first real-service checks)."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from redis import Redis
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.session import get_engine
from tests.support.integration_env import TEST_DB_NAME

# Synthetic Bangla/mixed-script samples: combining marks, ZWJ/ZWNJ, emoji ZWJ sequence, Latin.
UNICODE_SAMPLES = [
    "ক্ষ",
    "কি",
    "র‍্য",
    "ক্‌ষ",
    "👩‍👩‍👧",
    "বাংলা text, মিশ্র লিপি ✓",
]


@pytest.fixture(scope="module")
def scratch_table(db_engine: Engine) -> Iterator[str]:
    """A real (committed) table, since there are no models yet."""
    with db_engine.begin() as conn:
        conn.execute(text("CREATE TABLE harness_scratch (id serial PRIMARY KEY, note text)"))
    yield "harness_scratch"
    with db_engine.begin() as conn:
        conn.execute(text("DROP TABLE harness_scratch"))


def test_readiness_against_real_services(api_client: TestClient) -> None:
    resp = api_client.get("/api/v1/health/ready")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "checks": {"database": "ok", "queue": "ok"}}


def test_app_engine_points_at_throwaway_database(test_settings: Settings) -> None:
    name = get_engine().url.database
    assert name is not None and TEST_DB_NAME.fullmatch(name)


@pytest.mark.parametrize("run", [1, 2])
def test_each_test_starts_with_a_clean_database(
    db_session: Session, scratch_table: str, run: int
) -> None:
    count = text("SELECT count(*) FROM harness_scratch")
    assert db_session.execute(count).scalar_one() == 0
    db_session.execute(text("INSERT INTO harness_scratch (note) VALUES (:n)"), {"n": f"run {run}"})
    db_session.commit()  # code under test may commit; still rolled back afterwards
    assert db_session.execute(count).scalar_one() == 1


@pytest.mark.parametrize("sample", UNICODE_SAMPLES)
def test_unicode_round_trips_with_code_point_length(
    db_session: Session, scratch_table: str, sample: str
) -> None:
    row = db_session.execute(
        text("INSERT INTO harness_scratch (note) VALUES (:n) RETURNING note, char_length(note)"),
        {"n": sample},
    ).one()
    assert row[0] == sample
    assert row[1] == len(sample)  # code points, not bytes: database is UTF-8


@pytest.mark.parametrize("run", [1, 2])
def test_each_test_starts_with_an_empty_redis_db(
    redis_client: Redis, test_settings: Settings, run: int
) -> None:
    db_index = redis_client.connection_pool.connection_kwargs["db"]
    expected = Redis.from_url(test_settings.redis_url).connection_pool.connection_kwargs["db"]
    assert db_index == expected != 0
    assert redis_client.get("harness:key") is None
    redis_client.set("harness:key", str(run))
