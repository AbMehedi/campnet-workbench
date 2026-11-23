# Roadmap — small feature slices

Each item is one `/feature` run: plan → build → test → commit. Tick items when done and link the
plan file. Split anything that feels bigger than one sitting. Milestones follow the design doc §17.

## M1 — Backend foundation (finish)

- [x] M1-00 Repository scaffold: FastAPI, settings, health checks, worker, Compose, CI
- [ ] M1-01 Verify full Docker stack locally (compose up, migrate, health ready, frontend loads); fix anything found
- [ ] M1-02 Structured JSON logging with request IDs + standard error envelope (design §6.5, §14.1)
- [ ] M1-03 Integration test harness: pytest fixtures for a throwaway Postgres DB + Redis; run in CI with service containers
- [ ] M1-04 First migration: `users`, `projects`, `project_memberships` with roles (design §5.1, §5.3)
- [ ] M1-05 Worker health check: enqueue a no-op job and report worker status (design §14.2)

## M2 — Ingestion and media

- [ ] M2-01 `data_sources`, `import_batches`, `raw_records` models + migration
- [ ] M2-02 Apify JSON/JSONL parser with streaming + per-record validation report (synthetic fixtures)
- [ ] M2-03 Normalizer: raw record → `posts` (UTC timestamps, source metadata JSON); raw stays unchanged
- [ ] M2-04 Duplicate policy (`skip_existing`) + idempotent re-import test
- [ ] M2-05 Import API: upload file → import batch → queued job → status/report endpoint
- [ ] M2-06 Storage interface + local filesystem adapter (internal keys, MIME/size checks, no path traversal)
- [ ] M2-07 `media_assets` + `post_media` (ordering) + media registration/download job

## M3 — OCR and text correction

- [ ] M3-01 OCR adapter interface + fake adapter for tests
- [ ] M3-02 `ocr_runs` / `ocr_blocks` persistence and OCR job
- [ ] M3-03 Tesseract (`ben`) adapter — record engine/model versions
- [ ] M3-04 `text_revisions` + correction endpoint; Unicode offset test suite (Bangla, ZWJ/ZWNJ, emoji)

## M4 — Annotation (auth first)

- [ ] M4-01 Authentication (decide session model → ADR), Argon2id, login rate limit
- [ ] M4-02 Central project-scoped authorization + cross-project access tests
- [ ] M4-03 Codebook versions + technique labels (config-driven)
- [ ] M4-04 Annotation tasks, assignments, server-enforced state machine
- [ ] M4-05 Annotations + evidence (text span, image region) with validation
- [ ] M4-06 Frontend: login, task queue, post/media viewer
- [ ] M4-07 Frontend: text-span and image-region selection, submit annotation

## M5 — Review and export

- [ ] M5-01 Review / revision request / adjudication with preserved history
- [ ] M5-02 Audit events for key actions
- [ ] M5-03 JSONL/CSV export job + provenance manifest

## M6 — Release readiness

- [ ] M6-01 Choose license (ADR) and add LICENSE
- [ ] M6-02 Synthetic demo project + seed script
- [ ] M6-03 Backup/restore script and guide; deployment guide
