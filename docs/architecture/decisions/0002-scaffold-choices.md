# 2. Milestone 1 scaffold choices

Date: 2026-11-23
Status: Accepted

## Decision
- Python 3.14, dependencies managed and locked with uv (`backend/uv.lock`).
- Synchronous SQLAlchemy 2 with psycopg 3; async can be revisited if profiling demands it.
- The RQ worker lives in `backend/app/worker.py` and shares the backend image, instead of the
  separate top-level `worker/` directory sketched in §8, so jobs can import services and models
  without packaging the backend separately.
- Frontend scaffolded with Vite (React + TypeScript), linted with oxlint; `/api` is proxied to
  the backend in development.
- Compose binds every port to 127.0.0.1.
