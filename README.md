# CampNet Data Workbench

An open-source, reproducible platform for ingesting, processing, annotating, reviewing, and
exporting multimodal research datasets, with local and cloud deployment options.

> **Status:** Milestone 1 scaffold (backend foundation). Most features in the design are not
> implemented yet. The full design document is kept privately by the maintainers
> (`docs/private/DEVELOPER_DOCUMENTATION.md`, git-ignored); public decisions are recorded as ADRs
> in `docs/architecture/decisions/`.

**Open-source the infrastructure. Protect the research data. Make the methodology reproducible.**
Never commit real research data, media, annotations, or credentials to this repository.

## Stack

| Part      | Tech                                                    |
|-----------|---------------------------------------------------------|
| API       | Python 3.14, FastAPI, Pydantic, SQLAlchemy 2, Alembic   |
| Worker    | RQ on Redis — `backend/app/worker.py`, shares the backend image |
| Database  | PostgreSQL                                              |
| Frontend  | React + TypeScript (Vite)                               |
| Dev stack | Docker Compose                                          |

## Quick start (Docker)

```sh
cp .env.example .env          # then set APP_SECRET_KEY and POSTGRES_PASSWORD
docker compose up --build -d
docker compose exec backend alembic upgrade head
docker compose ps
```

- API: http://localhost:8000/api/v1/health/ready (docs at `/api/docs`)
- Frontend: http://localhost:5173

Stop with `docker compose down`. Avoid `down -v` unless you mean to delete the local database
and media volumes.

## Running without Docker

Requires [uv](https://docs.astral.sh/uv/) and Node.js 24+. Postgres and Redis must be running
(e.g. `docker compose up -d db redis`).

```sh
# backend
cd backend
uv sync
uv run uvicorn app.main:app --reload
uv run python -m app.worker          # in another terminal

# frontend
cd frontend
npm install
npm run dev
```

## Checks

```sh
cd backend && uv run ruff format --check . && uv run ruff check . && uv run mypy && uv run pytest
cd frontend && npm run lint && npm run build
```

## Layout

```
backend/     FastAPI app (app/), Alembic migrations, tests
             └─ app/worker.py   background worker (RQ), run with `python -m app.worker`
frontend/    React + TypeScript UI
configs/     Language packs and example configuration
docs/        Design documentation and architecture decision records (ADRs)
```

Modules are added as their milestone is implemented rather than created up front.

## License

Not yet chosen (see ADR backlog in `docs/architecture/decisions/`). Until a license is added,
no reuse rights are granted.
