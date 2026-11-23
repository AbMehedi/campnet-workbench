# AGENTS.md — working agreement for coding agents

CampNet Data Workbench: an open-source platform for ingesting, OCR-processing, annotating,
reviewing and exporting multimodal (Bangla-first) research datasets. Humans make every research
decision; the software preserves evidence and provenance.

## Non-negotiable rules

1. **No real research data or secrets, ever.** Don't commit or paste real posts, media, OCR output,
   annotations, `.env`, or credentials. Tests and fixtures use synthetic data only.
2. **Never push without the maintainer's explicit permission** — ask every time, for every push
   (including `gh pr create`). Local commits are fine. Never rewrite published history
   (force-push, amending pushed commits) unless the maintainer explicitly asks.
3. **Plan every feature together with the maintainer.** Don't pick scope, write a plan, or start
   implementing on your own: discuss the slice first, then get explicit approval of the written
   plan before any code.
4. **Raw data is immutable.** Raw records, OCR runs and submitted annotations are never updated in
   place; corrections create new revisions or events.
5. **Server is the authority** for permissions and workflow state; the frontend never decides.
6. **Don't leak internals** in API errors, health checks or logs: no stack traces, SQL, storage
   keys, paths, credentials, or post text.
7. **Small steps.** One feature slice per branch/PR, with tests. Don't scaffold modules ahead of
   need.

## Where things are

| Path | What |
|---|---|
| `backend/app/` | FastAPI app. Layering: `api/v1` (HTTP only) → `schemas` → `services` (business rules) → `repositories` → `models` |
| `backend/app/worker.py` | RQ background worker (`python -m app.worker`) |
| `backend/migrations/` | Alembic migrations; every model change needs one |
| `backend/tests/{unit,integration}` | pytest; `integration` marker needs Postgres/Redis |
| `frontend/src/` | React + TypeScript (Vite); `/api` proxied to the backend in dev |
| `configs/languages/` | Language packs (Bangla is `bn.yaml`) |
| `docs/architecture/decisions/` | ADRs — record decisions here |
| `docs/plans/` | Roadmap and one plan file per feature |
| `docs/private/` | **Git-ignored.** Full design doc `DEVELOPER_DOCUMENTATION.md`, if present locally. Read it for design intent; never copy it into tracked files wholesale. |

## Commands

```sh
# backend (run inside backend/)
uv sync
uv run ruff format . && uv run ruff check . && uv run mypy && uv run pytest -q
uv run pytest -q -m "not integration"          # without Docker
uv run alembic revision --autogenerate -m "..." # after model changes; review the file!
uv run alembic upgrade head

# frontend (run inside frontend/)
npm install
npm run lint && npm run build

# full stack (repo root)
cp .env.example .env    # once; set APP_SECRET_KEY, POSTGRES_PASSWORD
docker compose up --build -d
docker compose exec backend alembic upgrade head
docker compose ps && docker compose logs -f backend worker
```

Never run `docker compose down -v` unless told to — it deletes the local database and media.

## How we build features

Use the `/feature` skill (`.claude/skills/feature/SKILL.md`). In short:
**pick a slice from `docs/plans/ROADMAP.md` → write `docs/plans/NNNN-<slug>.md` → get the plan
approved → implement with tests → run all checks → update the roadmap → commit.**

A slice is done when (design doc §18): behavior and permissions are documented, validation and
failure behavior are defined, migrations are reviewed, critical paths have unit/integration
tests, nothing sensitive leaks, the frontend handles loading/empty/error states, audit/provenance
is recorded where required, and it works in the local Docker stack.

## Conventions

- Python 3.14, strict mypy, ruff (line length 100). Type everything.
- UUID primary keys; timestamps stored in UTC (`timestamptz`).
- API base path `/api/v1`; error envelope `{"error": {"code", "message", "details", "request_id"}}`.
- Text span offsets are Unicode code points into an immutable text revision; tests must include
  Bangla combining marks, ZWJ/ZWNJ, emoji and mixed script.
- Image regions use normalized 0–1 coordinates plus the source image dimensions.
- Commit messages: imperative summary line, then why. Reference the plan file.
- Open questions that change methodology → ask the maintainer and record an ADR; don't guess.
