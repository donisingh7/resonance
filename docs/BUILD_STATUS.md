# Resonance — Build Status

Last updated: 2026-09-27 (S1 foundation phase)

## Implemented

**Backend (FastAPI, `backend/app/`)**
- `GET /health` — returns `{"status": "healthy"}`
- `POST /projects` — creates a project (`name`, `description`), returns full
  `Project` object (`id`, `name`, `description`, `status`, `created_at`)
- `GET /projects/{project_id}` — returns a project by id, 404 if missing
- `POST /projects/{project_id}/upload` — accepts a single multipart file
  upload, validates extension against an allowlist
  (`mp3, wav, mp4, jpg, jpeg, png, pdf, txt`), stores it under
  `data/projects/{project_id}/uploads/` with a generated safe filename, and
  returns metadata (original filename, stored filename/path, file type,
  size, project id). Unsupported extensions return HTTP 400 with a clear
  message; unknown project ids return HTTP 404.

**Persistence**
- File-based, no database. Each project is a JSON file at
  `data/projects/{project_id}/project.json`. Uploaded files live in the
  project's `uploads/` subdirectory. `data/` is gitignored.

**Frontend (Streamlit, `frontend/app.py`)**
- Shows "Resonance" title and "Multimodal Experience Intelligence" caption
- Displays live backend health check result
- Form to create a project (name + description)
- Field to load an existing project by id
- Displays the active project's JSON
- Multi-file uploader for supported types, uploads each to the active
  project, and displays returned metadata in a table

## Current architecture

```
resonance/
├── backend/app/
│   ├── main.py            # FastAPI app, includes health + projects routers
│   ├── api/
│   │   ├── health.py
│   │   └── projects.py    # POST /projects, GET /projects/{id}, POST /projects/{id}/upload
│   ├── core/config.py     # Settings (pydantic-settings), data_dir path
│   ├── models/project.py  # Project, ProjectCreateRequest, UploadMetadata
│   └── services/storage.py # File-based create/get project, save_upload, extension allowlist
├── frontend/app.py
├── data/                  # gitignored, created at runtime
│   └── projects/{project_id}/project.json, uploads/
├── requirements.txt
├── .env.example
├── CLAUDE.md
└── docs/BUILD_STATUS.md
```

## Known limitations

- No database — file-based storage only; not safe for concurrent writers
  and has no indexing/listing of all projects (`GET /projects` list
  endpoint does not exist yet, only get-by-id).
- No authentication or authorization — anyone reaching the API can create
  projects and upload files.
- No file content validation beyond extension check (no magic-byte/MIME
  sniffing, no size limit enforced).
- No deduplication or cleanup of uploaded files.
- No automated test suite — verified via manual smoke pass only.
- Frontend keeps "active project" in Streamlit session state only; no
  project listing UI.
- Not containerized, not deployed anywhere.

## Next phase: multimodal ingestion & normalization

Planned scope (not started):
- Parse/normalize uploaded files into a consistent internal representation
  per modality (audio/video/image/document)
- Extract basic technical metadata (duration, dimensions, page count, etc.)
- Define a consistent internal schema for "ingested asset" independent of
  original file type

Explicitly out of scope until a future phase: AI/ML models (transcription,
OCR, vision, embeddings), database migration, authentication, deployment.
