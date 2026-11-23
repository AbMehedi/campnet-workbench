# Contributing

- Open an issue or discussion before substantial changes.
- Keep pull requests small and reviewable; include tests for changed behavior.
- Database changes need an Alembic migration and migration notes in the PR.
- Update documentation alongside code. Clearly separate implemented features from planned work.
- **Never** include real research data, media, annotations, or secrets in commits, screenshots,
  test fixtures, or issue reports. Use synthetic fixtures only.
- Run the checks listed in the README before pushing; CI runs the same ones.
- Record significant design decisions as ADRs in `docs/architecture/decisions/`.
