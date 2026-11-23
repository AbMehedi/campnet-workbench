# 1. Record architecture decisions

Date: 2026-11-23
Status: Accepted

## Context
The design (developer documentation v0.1, §19) leaves several decisions open for the research
and implementation team. Those choices affect methodology and must be deliberate and traceable.

## Decision
Record each significant decision as a numbered Markdown ADR in this directory.

## Open decisions (from §19), each to become its own ADR
1. Product and repository naming
2. Annotation protocol (per-post vs per-modality decisions; No Technique / Uncertain)
3. First machine-readable codebook version
4. Text offset convention (proposed: Unicode code points into an immutable revision)
5. Number of independent annotators per item
6. Review and adjudication roles
7. First S3-compatible storage provider
8. First OCR engine/model for Bangla
9. Browser authentication model and CSRF handling
10. Export schema and media handling
11. Software license (Apache-2.0 vs AGPL-3.0) and example-data rights
12. Deployment boundary (LAN/VPN vs public internet)
