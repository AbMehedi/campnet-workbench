# 0002 — Integration test harness (Postgres + Redis)
Roadmap: M1-03 · Status: done · Date: 2026-11-23
Branch: `feat/M1-03-integration-harness`, stacked on `feat/M1-02-logging-error-envelope`.

## Goal
Developers and CI can run `pytest -m integration` against real PostgreSQL and Redis, with each
test isolated, migrations exercised on every run, and no way for tests to touch dev data.

## Scope
- In:
  - Integration fixtures: throwaway UTF-8 Postgres database per session (migrated with Alembic),
    per-test transaction rollback, isolated Redis DB, API client wired to the test DB/Redis.
  - App caches re-pointed at test services for the whole integration session.
  - Skip-vs-fail policy for missing services (`CAMPNET_REQUIRE_INTEGRATION`) and safety guards.
  - First integration tests (readiness, isolation, Unicode round-trip, migrations, Redis).
  - CI job `backend-integration` with service containers; unit job runs `-m "not integration"`.
  - Compose `backend-test` service (profile `test`).
- Out (later slices): RQ job execution / worker tests (M1-05), model factories (M1-04+),
  storage-adapter tests (M2-06), parallel test runs (`pytest-xdist`).

## Design

### Configuration (test-only env vars, not in `Settings`)
- `TEST_DATABASE_URL` — admin URL to the maintenance DB (`…/postgres`); role needs `CREATEDB`.
- `TEST_REDIS_URL` — e.g. `redis://localhost:6379/15`.
- `CAMPNET_REQUIRE_INTEGRATION=1` — missing/unreachable services **fail** instead of skip (CI).

### `tests/support/integration_env.py` (pure functions, unit-tested without services)
- `load_integration_env(environ) -> IntegrationEnv | SkipReason`, honouring
  `CAMPNET_REQUIRE_INTEGRATION` (raises instead of returning a skip reason).
- `check_redis_url(test_url, app_url)`: DB index taken from
  `Redis.from_url(url).connection_pool.connection_kwargs["db"]` (handles `?db=`, `unix://`);
  refuse index 0 and refuse the same host/port/db as `REDIS_URL`.
- `check_admin_url(test_url, app_url)`: sanity check only — refuse if it equals `DATABASE_URL`
  and is not a maintenance DB.
- `TEST_DB_NAME = re.compile(r"campnet_test_[0-9a-f]{12}")` and `is_test_database_url(url)`.

### Fixtures (`tests/integration/conftest.py`)
- Marker: `pytest_collection_modifyitems` adds `integration` **only to items whose `item.path` is
  under this directory**.
- `integration_env` (session): load env; skip/fail; connectivity check (2 s timeout).
- `make_database` (session factory): via AUTOCOMMIT admin connection,
  `CREATE DATABASE campnet_test_<hex> TEMPLATE template0 ENCODING 'UTF8'`. Finaliser: assert
  name `fullmatch`es `TEST_DB_NAME`, then `DROP DATABASE … WITH (FORCE)`.
- `test_settings` (session, autouse within integration): create + migrate DB; set `DATABASE_URL`,
  `REDIS_URL` env to the test values; `cache_clear()` `get_settings`, `get_engine`,
  `get_sessionmaker`; assert `is_test_database_url(get_settings().database_url)`. Restored at
  session end. So *any* code path using the app's engine hits the throwaway DB.
- `db_engine` (session): `get_engine()` after the switch; disposed at end.
- `db_session` (function): outer `connection.begin()` +
  `Session(bind=connection, join_transaction_mode="create_savepoint")`; rolled back afterwards.
- `redis_client` (function): `flushdb()` before and after.
- `api_client` (function): `create_app(test_settings)`, `get_db` overridden to yield `db_session`.
  Comment: the client shares one connection — never use it concurrently.

### Small app changes for testability
- `migrations/env.py`: URL from `config.attributes["database_url"]` if given, else settings;
  engine built with `create_engine(url, poolclass=NullPool)` and offline mode uses `url`
  directly — no `set_main_option` (ConfigParser `%` interpolation breaks URL-encoded passwords;
  fixes an existing bug). Skip `fileConfig` when `config.attributes.get("configure_logger") is
  False`, so Alembic doesn't reset logging mid-test-session.
- `app/main.py`: `create_app` stores `app.state.settings`.
- `app/api/deps.py`: `get_app_settings(request) -> Settings` (from `app.state`).
- `app/db/redis.py`: `get_redis(settings = Depends(get_app_settings)) -> Redis`, clients cached
  per URL with `socket_connect_timeout=2` and `socket_timeout=2`.
- `api/v1/health.py`: readiness uses `get_redis`.

### CI (`.github/workflows/ci.yml`)
- `backend` job: `pytest -q -rs -m "not integration"`.
- New `backend-integration` job: services `postgres:18` and `redis:8`, both with health options;
  env `TEST_DATABASE_URL=…@localhost:5432/postgres` (CI-only synthetic password),
  `TEST_REDIS_URL=redis://localhost:6379/15`, `CAMPNET_REQUIRE_INTEGRATION=1`;
  `uv run pytest -q -rs -m integration` (pytest exit 5 on zero tests already fails the job).

### Compose
- New `backend-test` service, `profiles: [test]`, same image, `depends_on` healthy db/redis,
  env `TEST_DATABASE_URL=postgresql+psycopg://${POSTGRES_USER:-campnet}:${POSTGRES_PASSWORD}@db:5432/postgres`,
  `TEST_REDIS_URL=redis://redis:6379/15`, `CAMPNET_REQUIRE_INTEGRATION=1`; mounts `app`,
  `migrations`, `tests`, `pyproject.toml`; command
  `pytest -q -rs -m integration -p no:cacheprovider` (container user can't write `.pytest_cache`).
  Run: `docker compose --profile test run --rm backend-test`. Runtime `backend` env unchanged.
- `backend/tests/integration/README.md`: host and compose commands, the env vars, cleanup query
  for DBs leaked by killed runs (`SELECT datname FROM pg_database WHERE datname LIKE
  'campnet_test_%'` → drop manually), and "not safe for parallel runs (shared Redis DB)".

No models, migrations or endpoints added.

## Tests
- Unit (no services): auto-marker scoping (a unit test is selected under
  `-m "not integration"`); Redis guard (DB 0, `?db=0`, same-as-app refused; 15 accepted);
  skip vs fail under `CAMPNET_REQUIRE_INTEGRATION`; `TEST_DB_NAME` matching.
- Integration:
  - `/api/v1/health/ready` → 200 against real Postgres + Redis (test Redis DB).
  - App caches point at the throwaway DB (`get_engine().url.database` matches `TEST_DB_NAME`).
  - Isolation: one test run twice (parametrized) on a regular table created+committed in a
    session fixture: assert empty → insert → commit → assert visible.
  - Unicode: Bangla with combining marks (`ক্ষ`, `কি`), ZWJ/ZWNJ (`র‍্য`, `ক্‌ষ`), emoji ZWJ
    sequence and Latin round-trip byte-identical; `char_length` == Python `len`.
  - Migrations on a fresh DB: exactly one head; `upgrade head` → current == head;
    `downgrade base` → `upgrade head`; autogenerate drift check
    `compare_metadata(..., Base.metadata) == []`.
  - Redis: value from one parametrized run absent in the next; client DB index is the test one.
- Research-specific (§10.2 #11): CI uses no real data or secrets.

## Decisions (maintainer, 2026-11-23)
- Plan approved including advisor changes.
- Collation: roadmap item for an ADR before M2-03 (added as M2-00).
- Runtime image without dev deps: roadmap follow-up (added as M6-04).

## Risks / open questions
1. **Collation (maintainer):** test DBs use UTF-8 with the server's default locale. Bangla
   sorting/uniqueness (ICU vs libc) is undecided → ADR before M2-03 adds ORDER BY/unique text.
2. **Dev deps in the runtime image (maintainer):** Dockerfile `uv sync` installs pytest/mypy into
   the image the API runs from. Proposed follow-up slice: `--no-dev` production build target.
3. Docker in this agent session needs `sg docker` until the maintainer re-logs in.

## Outcome
- Implemented as planned: `tests/support/` (env guards, Alembic config), `tests/integration/`
  fixtures + README, `migrations/env.py` (URL injection without ConfigParser, no logging reset),
  `get_redis` dependency reading `app.state.settings`, CI `backend-integration` job, compose
  `backend-test` profile service.
- Advisor diff review (approve) follow-ups applied: env/cache switch is package-scoped so unit
  tests never see the test DB; `get_redis` moved to `app/api/deps.py` (layering) with a
  request-path-only Redis client; downgrade leaves no tables/enums; drift check uses env.py's
  `compare_type`; probes closed; unit readiness test stubs Redis too.
- Verified 2026-11-23: ruff, mypy strict; `pytest` 48 passed / 13 skipped without services;
  61 passed with TEST_* against local compose (no leftover `campnet_test_*` DBs, no
  ResourceWarnings); `docker compose --profile test run --rm backend-test` 13 passed.
- Deferred: worker/RQ execution tests (M1-05); parallel test runs.
