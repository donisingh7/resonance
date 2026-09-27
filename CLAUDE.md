# Resonance — Project Context

## Purpose

Resonance is a **Multimodal Experience Intelligence** platform. It ingests and
processes multimodal inputs (audio, video, images, documents) tied to
projects/events, with the long-term goal of extracting structured insight
from them. Early phases focus on foundation: API scaffolding, storage, and
upload handling — not AI/ML processing.

## Clean-room rule

This is an **independent clean-room project**. Never introduce, reference,
or reuse:
- Bosch code, data, or internal tooling
- Any proprietary/internal project names or material from prior employers

All code here must be original or from open-source/public sources with
compatible licensing.

## Architecture conventions

- **Backend**: FastAPI, modular under `backend/app/`:
  - `api/` — route modules (one file per resource: `health.py`, `projects.py`, `assets.py`)
  - `core/` — settings/config (`config.py`, pydantic-settings, reads `.env`)
  - `models/` — pydantic models (data shapes, not ORM — no DB yet): `project.py` (Project),
    `asset.py` (Asset, Modality, IngestionStatus, MODALITY_BY_EXTENSION — the single
    source of truth for which extensions are supported and their modality)
  - `services/` — business logic / persistence:
    - `storage.py` — file-based persistence only (projects + assets on disk).
      Owns the on-disk layout; no metadata extraction logic here.
    - `ingestion.py` — the normalization/ingestion service. Turns raw upload
      bytes into an `Asset` (hashing, MIME guess, per-modality technical
      metadata extraction). Keep future modality-specific extraction logic
      here, not in `storage.py` or `api/`.
- **Frontend**: Streamlit, single `frontend/app.py` for now. Talks to backend
  only via HTTP (`BACKEND_URL` env var), no direct imports from `backend/`.
- **Persistence**: lightweight file-based, under `data/projects/{project_id}/`.
  No database yet. Each project has `project.json`, an `uploads/` subdirectory
  (raw stored files), and an `assets/` subdirectory (one `{asset_id}.json` per
  ingested asset). `data/` is gitignored (runtime data, not source).
- Routers are included in `backend/app/main.py`; keep new endpoints as new
  router modules under `api/`, not inline in `main.py`.
- Never return absolute, machine-specific filesystem paths in API responses —
  `stored_path` is always relative to the repo root.

## Current stack

- Python, FastAPI + uvicorn (backend)
- Streamlit (frontend)
- pydantic / pydantic-settings (models + config)
- File-based local storage (no DB, no Docker, no queues)
- Metadata extraction (non-AI, technical only): Pillow (images), mutagen
  (audio), hachoir (video/mp4), pypdf (PDF page count), charset-normalizer
  (text encoding detection)
- No auth, no cloud deployment yet

## Coding rules

- Keep it simple; don't add abstractions, DB layers, or infra ahead of need.
- No AI/ML model integration (no Whisper, OCR, vision, LLM calls) until
  explicitly scoped in a future phase.
- No authentication, Docker, queues, or cloud deployment until explicitly
  scoped.
- Validate inputs at API boundaries (e.g. file extension allowlist for
  uploads); trust internal service code otherwise.
- Avoid heavy automated test suites at this stage — smoke-test manually per
  phase instructions instead, unless a phase explicitly asks for tests.
- Update `docs/BUILD_STATUS.md` whenever implemented functionality changes,
  and keep it honest — never document features that aren't actually built.

## High-level future phases

1. ~~Multimodal ingestion & normalization~~ — **done** (S2/R1): every upload
   becomes an `Asset` with non-AI technical metadata (see
   `docs/BUILD_STATUS.md` for exact fields per modality).
2. AI/ML processing (transcription, OCR, vision, embeddings) — model choice
   deferred, not started
3. Persistent database layer (replacing file-based storage)
4. Authentication & multi-user support
5. Reporting / insight generation
6. Deployment (containerization, cloud hosting)

Do not start a phase early — follow explicit instructions per step.
