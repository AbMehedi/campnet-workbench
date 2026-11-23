---
name: feature
description: Plan, build and test one small CampNet Workbench feature slice end to end — pick from docs/plans/ROADMAP.md, write a plan file, get approval, implement with tests, run all checks, update the roadmap, commit. Use when the user says "next feature", "build <feature>", "plan <feature>", or invokes /feature.
---

# /feature — one small slice, planned, built, tested

Arguments: optional feature name or roadmap ID (e.g. `/feature M2-01` or `/feature project model`).
With no argument, propose the first unchecked item in `docs/plans/ROADMAP.md`.

Follow the phases in order. There are **two mandatory stops** for the user: after Phase 0.5
(agree on the slice) and after Phase 1 (approve the written plan). Never skip either, never treat
silence as approval, and never push anything without the user's explicit permission.

## Phase 0 — Orient

1. Read `AGENTS.md` (rules) and `docs/plans/ROADMAP.md`.
2. If `docs/private/DEVELOPER_DOCUMENTATION.md` exists, read only the sections relevant to the
   slice (data model §5, API §6, workflows §4, tests §10). It is private: don't copy it into
   tracked files beyond short references like "design §5.3".
3. Check `git status` is clean and you're on `main`.

## Phase 0.5 — Consult the user (stop)

Before writing any plan, discuss the slice with the user:
- which roadmap item (or their own idea) and why now;
- your proposed scope in a few bullets — what's in, what's deferred;
- the key design choices or trade-offs, each with your recommendation;
- any research/methodology question only they can answer.

**Wait for the user's answer.** Adjust scope to their input. Only then create the branch
`feat/<id>-<slug>` and continue.

## Phase 1 — Plan (then stop)

Create `docs/plans/NNNN-<slug>.md` (next free number) from this template:

```markdown
# NNNN — <title>
Roadmap: <ID> · Status: proposed · Date: <YYYY-MM-DD>

## Goal
One or two sentences: what a user/developer can do after this slice.

## Scope
- In: ...
- Out (later slices): ...

## Design
Models / migrations, endpoints (method, path, role), services, worker jobs, UI — only what applies.

## Tests
- Unit: ...
- Integration (needs Docker): ...
- Research-specific checks from design §10.2 that apply: ...

## Risks / open questions
Anything that needs a maintainer decision (→ ADR).
```

Rules for a good slice: finishable in one sitting, ≤ ~400 changed lines excluding lockfiles,
independently testable, leaves `main` working. If bigger, split it and add the pieces to the
roadmap.

**Advisor review:** before showing the user, ask the `advisor` subagent to review the plan file
("Review the PLAN at docs/plans/NNNN-<slug>.md"). Apply its must-fix items, and include its
verdict and any unresolved points or maintainer questions in what you show the user.

Show the user the plan summary and **wait for approval or changes.** Set `Status: approved`
once agreed.

## Phase 2 — Build

- Tests first where practical (write the failing test, then the code).
- Respect layering: routes thin → services hold rules → repositories/models for data.
- Model change → `uv run alembic revision --autogenerate -m "<slug>"`, then read and fix the
  generated migration (naming, nullability, server defaults, downgrade).
- Synthetic fixtures only, under `backend/tests/fixtures/`.

## Phase 3 — Verify

Run and report actual output (don't claim success without it):

```sh
cd backend && uv run ruff format . && uv run ruff check . && uv run mypy && uv run pytest -q
cd frontend && npm run lint && npm run build        # if frontend touched
```

If Docker is usable (`docker info` works), also:

```sh
docker compose up --build -d
docker compose exec backend alembic upgrade head
docker compose exec backend pytest -q -m integration
curl -s localhost:8000/api/v1/health/ready
```

If Docker isn't available, say integration tests were skipped — don't hide it.

Walk the definition-of-done list in `AGENTS.md` and note anything not met.

**Advisor review:** ask the `advisor` subagent to review the DIFF (`git diff main...HEAD`,
plan file path included). Fix must-fix findings, re-run the checks above, and report any
findings you chose not to act on, with the reason.

## Phase 4 — Wrap up

1. Plan file: set `Status: done`, add a short "Outcome" section (what changed, anything deferred).
2. `docs/plans/ROADMAP.md`: tick the item; add any follow-up slices discovered.
3. Methodology/architecture decision made? Add an ADR in `docs/architecture/decisions/`.
4. Commit on the feature branch with a message referencing the plan file.
5. **Do not push or open a PR.** Ask the user explicitly ("Push `feat/...` and open a PR?") and
   act only on a clear yes. Never force-push unless the user explicitly asks.
6. Tell the user: what was built, test results, what's next on the roadmap.
