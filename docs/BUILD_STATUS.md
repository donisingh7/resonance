# Resonance — Build Status

Last updated: 2026-09-28 (S2 / R1 — multimodal ingestion and normalization)

## Implemented

**Backend (FastAPI, `backend/app/`)**
- `GET /health` — returns `{"status": "healthy"}`
- `POST /projects` — creates a project (`name`, `description`)
- `GET /projects/{project_id}` — returns a project by id, 404 if missing
- `POST /projects/{project_id}/upload` — accepts a single multipart file,
  validates extension, writes it to disk, **normalizes it into an `Asset`
  record**, and returns that `Asset`. Unsupported extensions → HTTP 400;
  unknown project id → HTTP 404.
- `GET /projects/{project_id}/assets` — lists all assets ingested for a
  project (sorted by `created_at`), 404 if project missing
- `GET /projects/{project_id}/assets/{asset_id}` — returns one asset, 404 if
  project or asset missing

**Asset model (`backend/app/models/asset.py`)**
Every uploaded file becomes an `Asset` with:
`id, project_id, original_filename, stored_filename, stored_path, modality,
mime_type, extension, size_bytes, sha256, created_at, ingestion_status,
technical_metadata`. `stored_path` is relative to the repo root, never an
absolute machine path. `ingestion_status` is `completed` or `failed`
(failed only if metadata extraction raised an unexpected exception; missing
individual fields are represented as `null` inside `technical_metadata`,
not as a failure).

Supported modalities and extensions:
- `audio`: mp3, wav
- `video`: mp4
- `image`: jpg, jpeg, png
- `document`: pdf, txt

**Ingestion/normalization service (`backend/app/services/ingestion.py`)**
Dedicated module, separate from project/file storage. For each modality,
extracts non-AI technical metadata using lightweight libraries, verified
against real generated sample files (ffmpeg-generated audio/video, Pillow
test images, a pypdf-generated PDF, a plain text file):
- **Image** (Pillow): `width`, `height`, `format`
- **Audio** (mutagen, mp3+wav): `duration_seconds`, `sample_rate`, `channels`
- **Video** (hachoir, mp4): `duration_seconds`, `width`, `height`, `fps`
  (`fps` was `null` in the ffmpeg-generated smoke test file — hachoir's mp4
  parser doesn't always expose frame rate; other fields extracted fine)
- **PDF** (pypdf): `page_count`
- **TXT** (charset-normalizer): `character_count`, `line_count`, `encoding`
  (detected, not assumed to be UTF-8)

All assets also get SHA-256 (over the uploaded bytes) and a guessed MIME
type (`mimetypes.guess_type`). Extraction failures are caught per-asset;
on failure `technical_metadata` contains an `error` field and
`ingestion_status` is `failed` — nothing else in the request fails.

**Persistence**
- Still file-based, no database. Layout per project:
  `data/projects/{project_id}/project.json`,
  `data/projects/{project_id}/uploads/{stored_filename}`,
  `data/projects/{project_id}/assets/{asset_id}.json`.

**Frontend (Streamlit, `frontend/app.py`)**
- Unchanged: title/caption, backend health, create/load project, multi-file
  upload.
- New: "Ingested assets" section — fetches and displays all assets for the
  active project (filename, modality, MIME type, size, ingestion status,
  technical metadata) after upload or on refresh.

## Current architecture

```
resonance/
├── backend/app/
│   ├── main.py             # includes health, projects, assets routers
│   ├── api/
│   │   ├── health.py
│   │   ├── projects.py     # POST /projects, GET /projects/{id}, POST /projects/{id}/upload
│   │   └── assets.py       # GET /projects/{id}/assets, GET /projects/{id}/assets/{asset_id}
│   ├── core/config.py
│   ├── models/
│   │   ├── project.py      # Project, ProjectCreateRequest
│   │   └── asset.py        # Asset, Modality, IngestionStatus, MODALITY_BY_EXTENSION
│   └── services/
│       ├── storage.py      # file-based persistence: projects + assets on disk
│       └── ingestion.py     # normalization: metadata extraction + Asset assembly
├── frontend/app.py
├── data/                    # gitignored, runtime
├── requirements.txt
├── CLAUDE.md
└── docs/BUILD_STATUS.md
```

## Known limitations

- No database — file-based storage only; `list_assets` reads every asset
  JSON file per request (fine at current scale, won't scale to large
  projects).
- No authentication/authorization.
- No file content validation beyond extension check (no magic-byte
  sniffing, no upload size limit).
- Video metadata (`fps` especially) depends on hachoir's mp4 parser
  coverage; some real-world files may return `null` for fields that a
  heavier tool (ffprobe, opencv) could extract. Accepted trade-off to avoid
  a heavy/system-level dependency at this phase.
- No deduplication of identical uploads (sha256 is stored but not checked
  against existing assets).
- No automated test suite — verified via one manual smoke pass covering
  all seven supported extensions plus one rejected extension.
- Not containerized, not deployed anywhere.

## Next phase (not started)

AI/ML processing (transcription, OCR, vision, embeddings) — explicitly out
of scope for this phase and not started. Also not started: database
migration, authentication, reporting, deployment.
