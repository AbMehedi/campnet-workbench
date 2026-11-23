# Integration tests

Tests in this directory are automatically marked `integration` and need PostgreSQL and Redis.
They never touch existing databases: each run creates throwaway `campnet_test_<hex>` databases
(UTF-8, migrated with Alembic) and drops them at the end, and uses a dedicated Redis DB.

## Environment

| Variable | Example | Notes |
|---|---|---|
| `TEST_DATABASE_URL` | `postgresql+psycopg://campnet:<pw>@localhost:5432/postgres` | Maintenance DB; role needs `CREATEDB` |
| `TEST_REDIS_URL` | `redis://localhost:6379/15` | Must not be DB 0 or equal `REDIS_URL`; flushed before/after each test |
| `CAMPNET_REQUIRE_INTEGRATION` | `1` | Fail instead of skip when services are missing (CI) |

Without the first two, integration tests are skipped (`-rs` shows why).

## Running

```sh
# Docker stack (from repo root; uses the stack's db/redis)
docker compose --profile test run --rm backend-test

# Host (inside backend/, with the compose stack running)
export TEST_DATABASE_URL="postgresql+psycopg://campnet:<POSTGRES_PASSWORD>@localhost:5432/postgres"
export TEST_REDIS_URL=redis://localhost:6379/15
uv run pytest -q -rs -m integration
```

`backend-test` mounts `app`, `migrations`, `tests` and `pyproject.toml`; dependency changes
(`uv.lock`) still need `docker compose build`.

## Caveats

- `POSTGRES_PASSWORD` is inserted into URLs unencoded: avoid `@`, `/`, `%`, `:` in local
  passwords (or URL-encode them).
- **Not safe for parallel runs** (`pytest-xdist`, two runs at once): they share the Redis DB.
- `api_client` shares one DB connection: don't use it concurrently.
- A killed run (SIGKILL) can leave databases behind. List and drop them manually:
  `SELECT datname FROM pg_database WHERE datname LIKE 'campnet_test_%';` then
  `DROP DATABASE "<name>" WITH (FORCE);` — only names matching `campnet_test_<12 hex>`.
