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
    - `storage.py` — file-based persistence only (projects, assets,
      processing results on disk). Owns the on-disk layout; no metadata
      extraction or AI logic here.
    - `ingestion.py` — the normalization/ingestion service. Turns raw upload
      bytes into an `Asset` (hashing, MIME guess, per-modality technical
      metadata extraction, no AI). Keep future modality-specific extraction
      logic here, not in `storage.py` or `api/`.
    - `processing.py` — the AI-processing orchestrator (S3). Takes an
      already-ingested `Asset` and produces a `ProcessingResult` by routing
      to the AI provider abstraction per modality. Document (PDF/TXT)
      extraction stays local/non-AI here; only audio transcription and
      image/frame analysis go through a provider.
    - `video_tools.py` — thin ffmpeg/ffprobe subprocess wrappers (probe
      duration, extract audio, extract keyframes). No AI, no persistence.
    - `ai_providers/` — provider abstraction: `base.py` (the `AIProvider`
      interface), `mock_provider.py` (deterministic default, no external
      calls), `__init__.py` (`get_ai_provider()` factory, provider selected
      via `settings.ai_provider`). Add a real provider as a new module here
      and register it in the factory; don't touch `processing.py`'s
      modality-dispatch logic to add a provider.
- **Frontend**: Streamlit, single `frontend/app.py` for now. Talks to backend
  only via HTTP (`BACKEND_URL` env var), no direct imports from `backend/`.
- **Persistence**: lightweight file-based, under `data/projects/{project_id}/`.
  No database yet. Each project has `project.json`, an `uploads/` subdirectory
  (raw stored files), an `assets/` subdirectory (one `{asset_id}.json` per
  ingested asset), and a `processing_results/` subdirectory (one
  `{result_id}.json` per processed asset). `data/tmp/` holds transient
  per-run scratch space (e.g. video keyframe/audio extraction); always
  clean it up in a `finally` block after use. `data/` is gitignored
  (runtime data, not source).
- **Processing result ids are deterministic**: `uuid5` of `(asset_id,
  provider_name)`. Re-processing the same asset with the same provider
  overwrites its existing result file rather than creating a duplicate —
  this is the project's idempotency strategy under file-based storage.
  Keep this if a real provider is added; don't switch to random ids.
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
  (audio), hachoir (video/mp4), pypdf (PDF page count/text), charset-normalizer
  (text encoding detection)
- AI processing (S3): provider-abstracted (`ai_providers/`); `MockAIProvider`
  is the default and only implemented provider — deterministic, no external
  calls or credentials required. ffmpeg/ffprobe (system binaries, not pip
  packages) used for video audio/keyframe extraction.
- No auth, no cloud deployment yet

## Coding rules

- Keep it simple; don't add abstractions, DB layers, or infra ahead of need.
- AI-dependent operations (transcription, vision) go through the
  `ai_providers` abstraction and default to `MockAIProvider`. Do not wire up
  a real cloud provider (credentials, Whisper, OCR, vision APIs, LLM calls)
  until explicitly scoped in a future phase — the interface exists so that
  can be added later without touching `processing.py`'s dispatch logic.
- Processing (S3) is per-asset only. Do not add cross-asset synthesis,
  sentiment, themes, embeddings, or reporting until explicitly scoped.
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
2. ~~Multimodal AI processing~~ — **done, mock-only** (S3/R2): every asset
   can be processed per-modality into a `ProcessingResult`
   (transcript/extracted_text/visual_description) via the provider
   abstraction. `MockAIProvider` is the only implemented provider — no real
   transcription/OCR/vision model is wired up yet.
3. Cross-modal / cross-asset intelligence (sentiment, themes, pain points,
   recommendations) — not started, deliberately deferred from S3
4. Persistent database layer (replacing file-based storage)
5. Authentication & multi-user support
6. Reporting / insight generation
7. Deployment (containerization, cloud hosting)

Do not start a phase early — follow explicit instructions per step.
