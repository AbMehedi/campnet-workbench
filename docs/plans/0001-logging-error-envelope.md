# 0001 — Structured JSON logging, request IDs, standard error envelope
Roadmap: M1-02 · Status: done · Date: 2026-11-23

## Goal
Every API request gets a request ID that appears in its JSON log lines, in the `X-Request-ID`
response header and in any error body. Every API error uses the standard envelope
`{"error": {"code", "message", "details", "request_id"}}` (design §6.5) and never leaks internals.

## Scope
- In:
  - JSON log formatter (stdlib `logging`) for API and worker.
  - Pure-ASGI request-ID middleware that also owns the unhandled-exception path.
  - Exception handlers producing the envelope; `AppError` + `ErrorCode`.
  - Worker log hardening (RQ job args / exception text).
  - ADR 0003 (traceback policy) + matching edit to AGENTS.md rule 6.
- Separate commit on this branch: tick M1-01 on the roadmap (maintainer confirmed done).
- Out (later slices): `job_id` in worker logs (M1-05), audit events (M5-02), frontend error UI,
  log shipping/rotation.

## Design

### Envelope contract
```json
{"error": {"code": "NOT_FOUND", "message": "Resource not found.", "details": [], "request_id": "…"}}
```
- `details` is **always a list** (empty unless validation errors / `AppError` details).
- `request_id` is always present; `null` outside a request.
- `message` is a fixed generic string per code for HTTP/500 errors — never `exc.detail`,
  never `str(exc)`. Only `AppError` supplies its own message.

### `app/core/logging.py`
- `request_id_var: ContextVar[str | None]` (default `None`).
- `JsonFormatter(service, include_traceback)` — one JSON object per line, `ensure_ascii=False`.
  Base fields: `timestamp` (UTC ISO 8601), `level`, `service` (`api`/`worker`), `logger`,
  `message`, `request_id` (always, may be null). Extra fields come from a single **allowlist**:
  `code`, `exc_type`, `method`, `path`, `status`, `duration_ms`. All other `extra` keys are dropped
  (RQ passes job `arguments`/`kwargs` as extra). `traceback` emitted only if `include_traceback`.
- `configure_logging(service, level, include_traceback)` — idempotent; installs **one tagged**
  stdout handler on root and removes only handlers it owns (keeps pytest `caplog`). For
  `uvicorn`/`uvicorn.error`: clear their handlers and set `propagate=True`; `uvicorn.access`
  disabled. Note: under `uvicorn --reload` the supervisor process's own lines stay plain text.

### `app/core/errors.py`
- `ErrorCode(StrEnum)`: `VALIDATION_ERROR`, `BAD_REQUEST`, `UNAUTHORIZED`, `FORBIDDEN`,
  `NOT_FOUND`, `METHOD_NOT_ALLOWED`, `INTERNAL_ERROR` (others added when a slice needs them;
  unknown 4xx → `BAD_REQUEST`, unknown 5xx → `INTERNAL_ERROR`).
- `AppError(Exception)`: `code`, `message`, `status_code`, `details`.
- `error_response(status, code, message, details, headers=None)` → `JSONResponse` with the
  envelope; reads `request_id_var`; does **not** set `X-Request-ID` (middleware owns it).
- `register_exception_handlers(app)`:
  - Starlette `HTTPException` → keep status and its headers (`Allow`, `WWW-Authenticate`).
  - `RequestValidationError` → 422 `VALIDATION_ERROR`; each detail
    `{"location": loc[0], "field": "<rest of loc joined by '.'>", "reason": msg}`; integer indices
    kept as `items.0.name`; body-level errors (`loc == ("body",)`) get `field: null`.
    pydantic `input`/`ctx` are never copied.
  - `AppError` → its own status/code/message/details.
  - `Exception` → fallback only (see middleware).

### `app/core/request_context.py` — `RequestContextMiddleware` (pure ASGI, outermost user middleware)
- Inbound `X-Request-ID` accepted iff `re.fullmatch(r"[A-Za-z0-9._-]{1,128}", value)`, else UUID4.
- Sets `request_id_var`; on `http.response.start` sets/replaces `X-Request-ID` (single owner,
  no duplicate header).
- **Catches unhandled exceptions itself** (Starlette's `ServerErrorMiddleware` sits outside user
  middleware and re-raises, so a 500 would otherwise lose the request ID and be logged twice by
  uvicorn): logs once at ERROR with `code=INTERNAL_ERROR`, `exc_type`, traceback only if enabled;
  sends the 500 envelope if the response has not started; does not re-raise.
- Access line in `finally` (`logger="campnet.access"`): `method`, `path` (no query string),
  `status` (500 if an exception escaped), `duration_ms`. Then resets the contextvar.

### Wiring
- `create_app(settings: Settings | None = None)` so tests can pass `app_env` without touching the
  `lru_cache`. Calls `configure_logging("api", ...)`, adds middleware, registers handlers. CORS
  gets `expose_headers=["X-Request-ID"]`.
- `app/worker.py`: `configure_logging("worker", ...)`; `Worker(..., log_job_description=False)`;
  `work(logging_level=settings.log_level)`. Outside development, a filter on `rq.worker` keeps only
  the first line of each message (RQ puts the formatted traceback, incl. exception text, into the
  message body).
- Dockerfile/compose uvicorn command: add `--no-access-log` (belt and braces).
- `log_level` becomes `Literal["DEBUG","INFO","WARNING","ERROR","CRITICAL"]`.

### Traceback policy (ADR 0003)
Tracebacks in logs only when `APP_ENV=development`. See open question 1 on the default.

No models, migrations, endpoints or frontend changes.

## Tests (unit, no Docker)
- Formatter: single-line valid JSON; base fields; UTC timestamp; Bangla message round-trips;
  non-allowlisted extra dropped; `request_id: null` outside a request; traceback only when enabled.
- Request ID: generated when absent; valid inbound echoed; invalid inbound replaced (too long,
  space, `"abc\n"` trailing newline); exactly one `X-Request-ID` header; same ID in header, body
  and log records.
- Access log: one line per request; `?q=secret` not logged; status 500 when handler raises.
- Envelope: 404 unknown route; 405 with `Allow`; 422 via test route (field/location/reason,
  submitted secret absent, body-level `field: null`, list index path); `AppError` passthrough;
  unhandled exception → 500, request ID present, no exception message/class in body, logged once;
  `ResponseValidationError` (test route returning a bad model containing a marker string) → 500,
  marker absent from body and non-dev logs; traceback in logs only with `app_env=development`.
- Worker: RQ filter truncates multi-line messages outside development.
- Existing health tests pass; `/health/ready` 503 body unchanged (not an error envelope).
- Integration: none new. Smoke on Docker: `curl -i` shows header; `docker compose logs backend
  worker` are JSON.

## Decisions (maintainer, 2026-11-23)
1. Tracebacks in logs only when `APP_ENV=development` (ADR 0003, AGENTS.md rule 6 amended).
2. Code default `app_env` becomes `production`; `.env.example` keeps `development`.
3. Inbound `X-Request-ID` accepted from any client (validated, correlation only); revisit with
   the deployment-boundary decision (ADR open decision 12).

## Outcome
- Implemented as designed: `app/core/logging.py`, `errors.py`, `request_context.py`; `main.py` and
  `worker.py` wired; `APP_ENV` code default `production`; uvicorn `--no-access-log`; ADR 0003;
  AGENTS.md rule 6 amended.
- Changes from advisor diff review: first-line filter moved to the handler so it covers all
  `rq.*` loggers (RQ logs traceback text on `rq.job`); CORS made outermost so cross-origin 500s
  are readable; invalid-JSON validation errors report `field: null`; uvicorn loggers follow
  `LOG_LEVEL`; test that RQ adds no handlers of its own.
- Verified: ruff, mypy strict, 35 unit tests; local uvicorn smoke (JSON logs, header, envelope).
- Docker stack (2026-11-23): `/health/ready` 200 with `X-Request-ID`; 404 returns the envelope
  with the inbound request ID. Container log output (`docker compose logs backend worker`) was not
  inspected — worker JSON logging is covered by unit tests only.
- Follow-up candidates: refuse to start in production with default `APP_SECRET_KEY`.
