# Resonance — Build Status

Last updated: 2026-09-28 (S3 / R2 — multimodal AI processing, mock provider)

## Implemented

**Backend (FastAPI, `backend/app/`)**
- `GET /health`
- `POST /projects`, `GET /projects/{project_id}`
- `POST /projects/{project_id}/upload` — ingests into an `Asset` (unchanged
  from S2)
- `GET /projects/{project_id}/assets`, `GET /projects/{project_id}/assets/{asset_id}`
- **New: `POST /projects/{project_id}/assets/{asset_id}/process`** —
  processes one asset per its modality and returns a `ProcessingResult`.
  Re-running this on the same asset (same provider) overwrites the previous
  result rather than creating a duplicate (deterministic `uuid5(asset_id,
  provider_name)` id) — the project's idempotency strategy under file-based
  storage.
- **New: `GET /projects/{project_id}/processing-results`** — lists all
  processing results for a project, sorted by `created_at`.
- **New: `GET /projects/{project_id}/processing-results/{result_id}`**

**ProcessingResult model (`backend/app/models/processing.py`)**
`id, project_id, asset_id, modality, status (completed|failed), provider,
created_at, extracted_text, transcript, visual_description,
modality_metadata, processing_metadata, error`. Unused fields per modality
are `null`. A modality-processing exception is caught and turned into a
`status="failed"` result with a message in `error` — it does not raise an
HTTP error for the request beyond normal 404s, and never corrupts the
project or other assets' results.

**AI provider abstraction (`backend/app/services/ai_providers/`)**
- `base.py` — `AIProvider` interface: `transcribe_audio(path)`,
  `analyze_image(path)`.
- `mock_provider.py` — `MockAIProvider`, the only implemented provider.
  **Deterministic placeholder output only** — clearly labeled
  `[mock transcript]` / `[mock description]` in every response, derived
  from real file facts (name, size, image dimensions/format) but **not**
  real speech-to-text or vision analysis of content.
- `__init__.py` — `get_ai_provider()` factory, selects via
  `settings.ai_provider` (env `AI_PROVIDER`, default `"mock"`). A real
  provider (e.g. a hosted transcription/vision API) can be added as a new
  module here and registered in the factory without touching
  `processing.py`. Not implemented this phase — no cloud credentials are
  integrated, and none are required to run the app.

**Per-modality processing (`backend/app/services/processing.py`)** — what
is genuinely real/local vs. what goes through the (currently mock) AI
provider:

| Modality | What happens | Real/local or via provider |
|---|---|---|
| PDF | `pypdf` extracts text per page; `extracted_text` = all pages joined, `modality_metadata.pages` = per-page `{page_number, text}` | **Real, local** — no AI |
| TXT | Reads raw bytes, decodes using the encoding recorded at ingestion (falls back to `charset-normalizer` detection), normalizes line endings | **Real, local** — no AI |
| Image | Loads the stored image, calls `provider.analyze_image()` for `extracted_text` (OCR-like) and `visual_description` | **Via provider — currently mock, not real OCR/vision** |
| Audio | Calls `provider.transcribe_audio()` on the stored file | **Via provider — currently mock, not real speech-to-text** |
| Video | `ffmpeg` extracts a mono 16kHz WAV audio track and up to 3 bounded keyframes (at ~10%/50%/90% of duration, from `Asset.technical_metadata` or an `ffprobe` fallback); audio goes through `transcribe_audio()`, each keyframe through `analyze_image()`; only this one asset's own audio+frames are combined into its single result | Frame/audio **extraction is real, local (ffmpeg)**; the transcription and per-frame descriptions are **via provider — currently mock** |

Temporary video audio/keyframe files are written under `data/tmp/{run-id}/`
(gitignored) and removed in a `finally` block after processing, whether it
succeeds or fails.

**Persistence** — unchanged file-based approach, extended:
`data/projects/{project_id}/processing_results/{result_id}.json` alongside
the existing `project.json`, `uploads/`, `assets/`.

**Frontend (Streamlit, `frontend/app.py`)**
- Unchanged: health check, create/load project, multi-file upload.
- Ingested assets are now shown as expandable panels (filename, modality,
  status) with a **"Process asset"** button, and — once processed — the
  transcript / extracted text / visual description / modality metadata for
  that asset.

## Current architecture

```
resonance/
├── backend/app/
│   ├── main.py
│   ├── api/
│   │   ├── health.py
│   │   ├── projects.py
│   │   ├── assets.py             # + POST /assets/{id}/process
│   │   └── processing_results.py # GET list + GET by id
│   ├── core/config.py            # + ai_provider, ai_api_key settings
│   ├── models/
│   │   ├── project.py
│   │   ├── asset.py
│   │   └── processing.py         # ProcessingResult, ProcessingStatus
│   └── services/
│       ├── storage.py            # + processing_results persistence, runtime_tmp_dir()
│       ├── ingestion.py
│       ├── processing.py         # per-modality orchestration (S3)
│       ├── video_tools.py        # ffmpeg/ffprobe subprocess wrappers
│       └── ai_providers/
│           ├── base.py
│           ├── mock_provider.py
│           └── __init__.py       # get_ai_provider() factory
├── frontend/app.py
├── data/                          # gitignored, runtime (includes data/tmp/)
├── requirements.txt
├── .env.example                   # + AI_PROVIDER, AI_API_KEY placeholder
├── CLAUDE.md
└── docs/BUILD_STATUS.md
```

## Known limitations

- **All transcription and vision output is deterministic mock text, not
  real AI analysis.** No real speech-to-text, OCR, or vision model is
  integrated. This is by design for this phase, not an oversight.
- Video `fps` and audio-in-video detection depend on the source file; a
  video with no audio stream (as in the smoke-tested sample) correctly
  produces `transcript: null` and `audio_extracted: false` rather than an
  error.
- `list_processing_results` reads every result JSON file per request — fine
  at current scale, won't scale to large projects (same trade-off as asset
  listing).
- Idempotency is keyed on `(asset_id, provider)`, not on file content —
  re-uploading identical bytes as a new asset and processing it creates a
  separate result, by design (each asset is independent).
- No authentication, no database, no queues, no containerization/deployment.
- No automated test suite — verified via one manual smoke pass (see below).

## Smoke-tested this phase

TXT, PDF, JPG, MP3, and MP4 (video with no audio track) assets were
uploaded and processed end-to-end against `MockAIProvider`; list/get
processing-result endpoints; re-processing an asset confirmed to overwrite
rather than duplicate; a deliberately corrupt "PDF" confirmed to produce a
clean `status: "failed"` result with an `error` message instead of
crashing; existing project/upload/asset flows re-verified unaffected;
Streamlit boots.

## Next phase (not started)

Cross-modal / cross-asset intelligence: sentiment, top themes, pain points,
recommendations, questionnaires, executive reports, embeddings/vector
search, RAG. Also not started: database migration, authentication, cloud
deployment, queues.
