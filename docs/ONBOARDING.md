# Onboarding guide — CampNet Data Workbench

> A senior-to-junior walkthrough: what we are building, how it is put together, what is done, and
> how we work. Read it once now, and again after you've opened the files it links to.
>
> Snapshot as of 2026-11-24 (end of M1-03). The source of truth for status is
> [`plans/ROADMAP.md`](plans/ROADMAP.md); for rules, [`../AGENTS.md`](../AGENTS.md).

---

## 1. What is this project?

CampNet Data Workbench is an **open-source platform for research datasets**. Researchers collect
social-media posts (often with images, mostly in **Bangla**) and need to:

1. **Ingest** them (e.g. an Apify scraper export in JSON/JSONL),
2. **OCR** the images so text inside them becomes searchable and annotatable,
3. **Annotate** posts — label techniques using a codebook, marking evidence as text spans or
   image regions,
4. **Review** annotations (accept, request revision, adjudicate),
5. **Export** a clean dataset with a provenance manifest so the research is reproducible.

The motto: **open-source the infrastructure, protect the research data, make the methodology
reproducible.**

The key mental model: **humans make every research decision; the software preserves evidence and
provenance.** We are not building an "AI that labels things." We are building a tool that records
who did what, when, and on which version of the data.

---

## 2. Rules you must never break

These come from `AGENTS.md`. Most blocked reviews break one of them.

| # | Rule | Why it matters |
|---|------|----------------|
| 1 | **No real research data or secrets in the repo.** Tests use synthetic data only. | The data is sensitive; git history is forever. |
| 2 | **Never push without the maintainer's explicit OK.** Local commits are fine. | The maintainer controls what becomes public. |
| 3 | **Plan every feature with the maintainer first** — agree scope → written plan approved → code. | Research methodology decisions belong to humans. |
| 4 | **Raw data is immutable.** Corrections create new revisions/events, never `UPDATE` in place. | Reproducibility: you must always see what the original was. |
| 5 | **Server is the authority** for permissions and workflow state. | The frontend can be bypassed. |
| 6 | **Don't leak internals** — no stack traces, SQL, paths, storage keys or post text in API errors/logs. | Exception text can contain research data or infra details. |
| 7 | **Small steps** — one feature slice per branch, with tests, no scaffolding ahead of need. | Reviewable, revertable changes. |

---

## 3. The tech stack (and why)

| Layer | Technology | Why |
|---|---|---|
| API | **Python 3.14 + FastAPI** | Type hints, automatic validation via Pydantic, OpenAPI for free |
| Validation/config | **Pydantic / pydantic-settings** | One typed `Settings` object from environment variables |
| ORM | **SQLAlchemy 2 (sync) + psycopg 3** | Mature, explicit. Sync chosen deliberately (ADR 0002); async only if profiling demands it |
| Migrations | **Alembic** | Every model change ships with a reviewed migration |
| Database | **PostgreSQL 18** | Relational integrity, JSONB, good Unicode support |
| Background jobs | **RQ on Redis** | Simple job queue for long tasks: imports, OCR, exports |
| Frontend | **React 19 + TypeScript + Vite**, linted with **oxlint** | Fast dev server; `/api` proxied to the backend |
| Dev environment | **Docker Compose** | One command for the full stack; ports bound to `127.0.0.1` only |
| Tooling | **uv** (locking), **ruff** (format + lint), **mypy --strict**, **pytest** | Everything typed and checked in CI |

---

## 4. Architecture

### 4.1 Runtime view

```
 Browser (React, :5173)
     │  fetch /api/...   (Vite proxy in dev)
     ▼
 FastAPI backend (:8000) ──── SQLAlchemy ────► PostgreSQL
     │                                           ▲
     │ enqueue job                               │
     ▼                                           │
   Redis ◄──── RQ worker (python -m app.worker) ─┘
               (same image as the backend)
```

- The **API** handles short HTTP requests.
- Anything slow (importing a large file, OCR on thousands of images, building an export) is
  **enqueued** in Redis and executed by the **worker**.
- The worker lives in `backend/app/worker.py` and **shares the backend image** (ADR 0002), so jobs
  import the same services and models.

### 4.2 Code layering inside `backend/app/`

```
api/v1/        HTTP only: routing, request parsing, status codes
   │
schemas/       Pydantic request/response models (the API contract)
   │
services/      Business rules: permissions, workflow states, validation
   │
repositories/  Database queries
   │
models/        SQLAlchemy tables
```

**Rule of thumb:** a route function should be thin. If you are writing an `if` about business
logic inside `api/v1/`, it belongs in `services/`.

`schemas/`, `services/` and `repositories/` don't exist yet — rule 7 says we create them when a
feature needs them (expected from M1-04).

### 4.3 What exists in `backend/app/`

| File | What it does |
|---|---|
| `main.py` | `create_app()` factory: configures logging, adds middleware (CORS outermost, then request context), registers error handlers, mounts `/api/v1`. API docs are **disabled in production**. |
| `core/config.py` | `Settings` from environment variables. **`APP_ENV` defaults to `production`** — the safe mode; development must be opted into (ADR 0003). |
| `core/request_context.py` | Pure ASGI middleware: assigns/validates `X-Request-ID`, writes the access log, catches unhandled exceptions so even a 500 keeps its request ID. |
| `core/logging.py` | JSON-lines logger with an **allowlist** of extra fields, so a library can't accidentally log job arguments or post text. |
| `core/errors.py` | The standard **error envelope** and `AppError` (see below). |
| `api/v1/health.py` | `/health/live` (process up) and `/health/ready` (database + Redis reachable). Returns `ok`/`unavailable`, never error details. |
| `db/session.py`, `db/redis.py` | Engine, sessionmaker, `get_db` dependency, Redis client. |
| `worker.py` | RQ worker. Outside development, trims RQ tracebacks to the first line and doesn't log job descriptions. |

### 4.4 The error envelope — learn this pattern

Every error the API returns has the same shape:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "The request contains invalid fields.",
    "details": [{"location": "body", "field": "name", "reason": "Field required"}],
    "request_id": "3f6c..."
  }
}
```

- `code` is stable and machine-readable; the frontend switches on it.
- `message` is fixed per code — **we never put `str(exc)` in a response.**
- Validation details **don't echo submitted values** (they could be post text).
- `request_id` matches the `X-Request-ID` header and the log line. That is how we debug
  production without tracebacks.

In a service, raise expected failures like this:

```python
raise AppError(ErrorCode.FORBIDDEN, "You are not a member of this project.", status_code=403)
```

---

## 5. Domain concepts you'll meet soon

Details live in the private design doc (`docs/private/DEVELOPER_DOCUMENTATION.md`, git-ignored —
read it locally, never copy it into tracked files).

| Concept | Meaning |
|---|---|
| **Project / membership / role** | Everything is project-scoped. A user can be annotator in one project and reviewer in another. |
| **Raw record → Post** | The raw import row is stored untouched; a normalizer creates the `posts` row from it. |
| **Media asset** | Image/video linked to a post (ordered), stored via a storage interface (local filesystem now, S3-compatible later). |
| **OCR run / OCR block** | One execution of an OCR engine (engine/model versions recorded) and the text blocks it produced. |
| **Text revision** | Immutable version of a post's text. Corrections create a new revision. |
| **Annotation + evidence** | A label plus proof: a **text span** (Unicode code-point offsets into a specific text revision) or an **image region** (normalized 0–1 coordinates plus image dimensions). |
| **Codebook version** | The versioned label set annotators use. |
| **Language pack** | `configs/languages/bn.yaml`: NFC normalization, Tesseract `ben`, offsets in code points. |

### Why Bangla makes text handling hard

Bangla uses **combining marks** (vowel signs like `ি`, `া`), conjuncts via the virama `্`, and
**ZWJ/ZWNJ** (zero-width joiner/non-joiner). One visible "letter" can be several code points.
JavaScript string indexes count **UTF-16 code units**; Python counts **code points**. If frontend
and backend disagree on offsets, an annotation silently highlights the wrong text. That is why the
convention is **code points**, and tests **must** include Bangla combining marks, ZWJ/ZWNJ, emoji
and mixed script.

---

## 6. What we've done so far (Milestone 1)

| Item | Commit(s) | What it gave us |
|---|---|---|
| **M1-00** Scaffold | `83d3477` | FastAPI app, settings, health checks, worker, Compose, CI |
| Agent workflow | `66883fd` | `AGENTS.md`, `/feature` skill, `advisor` reviewer agent, roadmap |
| **M1-01** Docker stack verified | `fa6a5ce` | `compose up` → migrate → health ready → frontend loads |
| **M1-02** Logging + error envelope | `bb5ec8d` (PR #1) | JSON logs, request IDs, standard errors, ADR 0003 |
| **M1-03** Integration test harness | `ddfe8cb` | pytest fixtures creating a **throwaway Postgres DB** (`campnet_test_<hex>`) and using **Redis DB 15**; runs in CI with service containers |

### Decisions recorded (ADRs in `architecture/decisions/`)

- **0001** — We record architecture decisions as ADRs.
- **0002** — Scaffold choices: uv, sync SQLAlchemy, worker shares backend image, Vite + oxlint,
  localhost-only ports.
- **0003** — Tracebacks in logs **only** when `APP_ENV=development`; default environment is
  `production`.

### CI (`.github/workflows/ci.yml`)

Four jobs: backend (ruff format check, ruff, mypy, unit tests) · backend-integration (real
Postgres + Redis service containers) · frontend (lint + build) · compose (`docker compose build`).

### Frontend today

A single page that calls `/api/v1/health/ready` and shows the result. Even this tiny page handles
**loading, error and success** states — do the same in every screen you build.

---

## 7. Where we're going

Full list: [`plans/ROADMAP.md`](plans/ROADMAP.md). One checkbox = one `/feature` run.

| Milestone | Focus |
|---|---|
| **M1 Foundation** (finishing) | 04 users/projects/memberships · 05 worker health · 06 refuse default secret in production |
| **M2 Ingestion** | Collation ADR · raw records · Apify parser · normalizer · duplicate policy · import API · storage · media |
| **M3 OCR** | Adapter interface + fake · runs/blocks · Tesseract `ben` · text revisions + Unicode offset tests |
| **M4 Annotation** | Auth ADR + Argon2id · project authorization · codebooks · tasks/state machine · evidence · UI |
| **M5 Review & export** | Review/adjudication · audit events · JSONL/CSV export + provenance manifest |
| **M6 Release** | License ADR · synthetic demo seed · backup/restore · production image |

**Next up is M1-04**: the first real migration (`users`, `projects`, `project_memberships` with
roles). Everything after it depends on "who is in which project with which role."

### Our goals as developers

1. **Correctness of research evidence over speed.** A wrong offset or a lost revision can
   invalidate a study.
2. **Safe by default.** Production mode is the default, nothing leaks, ports are local-only.
3. **Reproducible.** Locked dependencies, migrations, provenance manifests on export.
4. **Small, reviewed, tested slices** that each work in the local Docker stack.
5. **Ship v1 (M6)** with a synthetic demo so others can adopt the platform without seeing real
   data.

---

## 8. How we build a feature

```
pick slice from ROADMAP
   → discuss scope with maintainer         (STOP 1: agree)
   → branch feat/<id>-<slug>
   → write docs/plans/NNNN-<slug>.md       (STOP 2: approve)
   → implement + tests
   → advisor agent reviews the diff
   → ruff / mypy / pytest / npm lint+build / Docker smoke test
   → tick roadmap, commit (imperative subject + why + plan reference)
   → ASK before pushing / opening a PR
```

See [`plans/0001-logging-error-envelope.md`](plans/0001-logging-error-envelope.md) and
[`plans/0002-integration-test-harness.md`](plans/0002-integration-test-harness.md) for good plan
examples, and `.claude/skills/feature/SKILL.md` for the full procedure.

### Definition of done (design §18)

Behavior and permissions documented · validation and failure behavior defined · migrations
reviewed (not just autogenerated) · critical paths have unit and integration tests · nothing
sensitive leaks · frontend handles loading/empty/error states · audit/provenance recorded where
required · works in the local Docker stack.

---

## 9. Your first day: commands

```sh
# one-time
cp .env.example .env            # set APP_SECRET_KEY and POSTGRES_PASSWORD

# run everything
docker compose up --build -d
docker compose exec backend alembic upgrade head
curl localhost:8000/api/v1/health/ready      # expect {"status":"ok",...}
# then open http://localhost:5173 in a browser

# backend checks (inside backend/)
uv sync
uv run ruff format . && uv run ruff check . && uv run mypy && uv run pytest -q
uv run pytest -q -m "not integration"        # without Docker

# integration tests against the compose db/redis
docker compose --profile test run --rm backend-test

# frontend checks (inside frontend/)
npm install && npm run lint && npm run build
```

⚠️ **Never run `docker compose down -v`** unless told to — it deletes the local database and
media volumes.

---

## 10. Suggested reading order

1. `AGENTS.md` — the rules.
2. `backend/app/main.py` → `core/request_context.py` → `core/errors.py` → `core/logging.py` —
   follow one request end to end.
3. [`architecture/decisions/0003-traceback-logging-policy.md`](architecture/decisions/0003-traceback-logging-policy.md)
   — why logging is so strict.
4. `backend/tests/integration/conftest.py` — how throwaway databases are created and dropped.
5. [`plans/ROADMAP.md`](plans/ROADMAP.md), then the private design doc §5 (data model) to prepare
   for M1-04.

**Exercise:** run `curl -H 'X-Request-ID: hello-123' localhost:8000/api/v1/nope`. Confirm the 404
envelope contains `"request_id": "hello-123"`, then find the same ID in
`docker compose logs backend`. Once you understand why that works, you understand the foundation.
