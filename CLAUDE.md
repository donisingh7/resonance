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
    source of truth for which extensions are supported and their modality),
    `intelligence.py` (ProjectIntelligence, EvidenceItem, IntelligenceStatus —
    the S4 cross-asset synthesis result and its evidence trail)
  - `services/` — business logic / persistence:
    - `storage.py` — file-based persistence only (projects, assets,
      processing results, project intelligence on disk). Owns the on-disk
      layout; no metadata extraction or AI logic here.
    - `ingestion.py` — the normalization/ingestion service. Turns raw upload
      bytes into an `Asset` (hashing, MIME guess, per-modality technical
      metadata extraction, no AI). Keep future modality-specific extraction
      logic here, not in `storage.py` or `api/`.
    - `processing.py` — the AI-processing orchestrator (S3). Takes an
      already-ingested `Asset` and produces a `ProcessingResult` by routing
      to the AI provider abstraction per modality. Document (PDF/TXT)
      extraction stays local/non-AI here; only audio transcription and
      image/frame analysis go through a provider.
    - `intelligence.py` — the cross-asset consolidation service (S4). Loads
      a project's completed `ProcessingResult`s, builds a bounded per-asset
      text context (skipping empty content, capping asset count/chars),
      calls `provider.synthesize_project()`, and persists a
      `ProjectIntelligence`. Provider failures are caught and turned into a
      `status="failed"` result, mirroring `processing.py`. All API-facing
      logic for this phase lives here, not in `api/intelligence.py`.
    - `video_tools.py` — thin ffmpeg/ffprobe subprocess wrappers (probe
      duration, extract audio, extract keyframes). No AI, no persistence.
    - `ai_providers/` — provider abstraction: `base.py` (the `AIProvider`
      interface: `transcribe_audio`, `analyze_image`, and — since S4 —
      `synthesize_project` for cross-asset synthesis), `mock_provider.py`
      (deterministic default, no external calls), `__init__.py`
      (`get_ai_provider()` factory, provider selected via
      `settings.ai_provider`). Add a real provider as a new module here
      and register it in the factory; don't touch `processing.py`'s or
      `intelligence.py`'s dispatch logic to add a provider.
- **Frontend**: Streamlit, single `frontend/app.py` for now. Talks to backend
  only via HTTP (`BACKEND_URL` env var), no direct imports from `backend/`.
- **Persistence**: lightweight file-based, under `data/projects/{project_id}/`.
  No database yet. Each project has `project.json`, an `uploads/` subdirectory
  (raw stored files), an `assets/` subdirectory (one `{asset_id}.json` per
  ingested asset), a `processing_results/` subdirectory (one
  `{result_id}.json` per processed asset), and an `intelligence/`
  subdirectory (one `{intelligence_id}.json` per generated project
  intelligence result). `data/tmp/` holds transient per-run scratch space
  (e.g. video keyframe/audio extraction); always clean it up in a `finally`
  block after use. `data/` is gitignored (runtime data, not source).
- **All JSON persistence in `storage.py` reads/writes with `encoding="utf-8"`
  explicitly.** `Path.write_text`/`read_text` default to the OS locale
  encoding, which on Windows (cp1252) cannot represent arbitrary Unicode
  (e.g. real extracted document content, or non-ASCII filenames/summary
  text) and raises `UnicodeEncodeError`. Always pass `encoding="utf-8"` for
  any new text file read/write in this codebase.
- **Processing result ids are deterministic**: `uuid5` of `(asset_id,
  provider_name)`. Re-processing the same asset with the same provider
  overwrites its existing result file rather than creating a duplicate —
  this is the project's idempotency strategy under file-based storage.
  Keep this if a real provider is added; don't switch to random ids.
- **Project intelligence ids are deterministic** the same way: `uuid5` of
  `(project_id, provider_name)`. Regenerating intelligence for the same
  project/provider overwrites the previous result rather than
  accumulating duplicates — same idempotency strategy as processing
  results, applied one level up.
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
- AI processing (S3) and cross-asset intelligence (S4): both
  provider-abstracted (`ai_providers/`); `MockAIProvider` is the default and
  only implemented provider — deterministic, no external calls or
  credentials required. ffmpeg/ffprobe (system binaries, not pip packages)
  used for video audio/keyframe extraction.
- No auth, no cloud deployment yet

## Coding rules

- Keep it simple; don't add abstractions, DB layers, or infra ahead of need.
- AI-dependent operations (transcription, vision) go through the
  `ai_providers` abstraction and default to `MockAIProvider`. Do not wire up
  a real cloud provider (credentials, Whisper, OCR, vision APIs, LLM calls)
  until explicitly scoped in a future phase — the interface exists so that
  can be added later without touching `processing.py`'s dispatch logic.
- Processing (S3) is per-asset only; cross-asset synthesis (S4, see below)
  is a separate service layer on top of it, not folded into `processing.py`.
  Do not add embeddings, vector search, RAG, questionnaires, or executive
  reporting until explicitly scoped.
- Cross-asset intelligence (S4) evidence must never be invented: every
  `EvidenceItem` persisted must reference a real `asset_id` /
  `processing_result_id` that was actually part of the synthesis input, and
  any `excerpt` must be a genuine substring of that asset's own processed
  text. `intelligence.py` defensively drops any evidence a provider returns
  that doesn't reference an id from the input context.
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
3. ~~Cross-asset intelligence~~ — **done, mock-only** (S4/R3): a
   project-level `ProjectIntelligence` (summary, themes, sentiment, pain
   points, positive signals, questions, opportunities, recommended actions)
   is synthesized across a project's completed `ProcessingResult`s, with
   every insight traceable to source assets via `EvidenceItem`s. Still
   mock-only — no real LLM synthesis, no embeddings/vector search/RAG.
4. Questionnaire generation / executive PDF report / management report —
   not started, deliberately deferred from S4
5. Persistent database layer (replacing file-based storage)
6. Authentication & multi-user support
7. Deployment (containerization, cloud hosting)

Do not start a phase early — follow explicit instructions per step.
