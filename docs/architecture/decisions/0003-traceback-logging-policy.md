# 3. Traceback logging policy and safe default environment

Date: 2026-11-23
Status: Accepted

## Context
AGENTS.md rule 6 forbids stack traces in API errors, health checks **and logs**. Applied strictly,
an unhandled 500 leaves only an exception class name to debug from. Exception messages and
tracebacks can contain SQL, storage paths or post text, so they must not reach logs of
deployments that process real research data. `APP_ENV` previously defaulted to `development`,
so a deployment that forgot to set it would also expose the OpenAPI docs.

## Decision
- API error bodies never contain stack traces or exception text, in any environment.
- Logs include a full traceback **only when `APP_ENV=development`**. In `test` and `production`,
  an unhandled error is logged with `code`, `exc_type` and `request_id` only — never `str(exc)`.
- The worker follows the same rule: outside development, RQ log messages are cut to their first
  line (RQ embeds the traceback in the message) and job descriptions (argument reprs) are not
  logged.
- The code default for `APP_ENV` is `production`; `.env.example` sets `development` for local
  work, so the unsafe mode must be chosen explicitly.

## Limitations
"Never `str(exc)`" is guaranteed for our own handlers. Third-party libraries that format an
exception into the log message on one line (e.g. RQ logging a Redis `ConnectionError` with `%s`)
can still include exception text; the first-line filter does not remove it. Treat such cases as
bugs when found and filter them specifically.

## Consequences
- Production debugging relies on request IDs and stable error codes; reproduce locally for
  tracebacks.
- Researchers must not run `APP_ENV=development` against real data.
- AGENTS.md rule 6 is amended to reference this ADR.
