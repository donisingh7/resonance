# Resonance — Deployment Readiness (not a deployment)

This document prepares the repository for a later deployment phase (P1+).
**Resonance is not deployed anywhere as of S7** — this is documentation
only, written so that step can be short and mechanical when it happens.

## Hosting constraint you must not ignore

**Persistence is local file-based storage** (`data/projects/{project_id}/…`
on whatever filesystem the backend process runs on — see `CLAUDE.md`). There
is no database and no object storage integration yet. This means:

- The backend **requires a persistent filesystem or attached volume**.
  Every uploaded file, `ProcessingResult`, `ProjectIntelligence`,
  `Questionnaire`, `ExecutiveReport`, and generated PDF lives under
  `data/`, and is lost if that storage isn't durable.
- **Do not deploy this to a platform with an ephemeral/read-only
  filesystem** (e.g. a typical serverless function runtime, or a container
  without a mounted volume) and expect data to survive a redeploy, scale
  event, or restart. That would silently lose user data — treat this as a
  hard blocker, not a tuning detail.
- Two realistic paths forward, neither implemented yet:
  1. Deploy on infrastructure with a persistent volume (a VM, a container
     platform with a durable mount, etc.) and keep the current file-based
     storage as-is.
  2. Replace `backend/app/services/storage.py`'s file-based implementation
     with a database/object-storage backend (this is explicitly deferred —
     see `CLAUDE.md`'s future-phases list — not a small change, since every
     service currently calls `storage.py` functions directly).

Until one of those is done, **do not present this as production-deployed**
or assume any hosting environment's local disk is durable by default.

## Backend

**Start command** (production-style, no `--reload`):

```bash
uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000
```

(`--app-dir backend` mirrors how this project has been run locally
throughout development; equivalently, `cd backend && uvicorn app.main:app
--host 0.0.0.0 --port 8000`.)

**Required/relevant environment variables** (see `.env.example` for the
authoritative list with defaults):

| Variable | Purpose | Notes |
|---|---|---|
| `APP_NAME` | FastAPI app title | cosmetic |
| `ENVIRONMENT` | free-text environment label | cosmetic; not used for branching logic today |
| `BACKEND_HOST` / `BACKEND_PORT` | bind address | the actual `uvicorn` command above takes precedence over these; keep them consistent |
| `AI_PROVIDER` | provider selection | only `"mock"` (`MockAIProvider`) is implemented — see Known Limitations below |
| `AI_API_KEY` | placeholder for a future real provider | **must stay unset** until a real provider is implemented; never commit a real value |
| `MAX_UPLOAD_SIZE_MB` | upload size guardrail | enforced at `POST /projects/{id}/upload`; raise for real-world audio/video files |

**Runtime storage assumption**: the process needs read/write access to
`data_dir` (defaults to `<repo>/data`, configurable only via
`Settings.data_dir` in `backend/app/core/config.py` — there's no `.env`
override for it yet, which is worth adding if `data_dir` needs to point
outside the repo in a deployed environment). Whatever filesystem backs
`data_dir` must be durable across restarts (see hosting constraint above).

**Health / readiness endpoints**:
- `GET /health` — process is up and serving requests. Always `200` if the
  process is alive.
- `GET /ready` — structured readiness: `200` when every *required* check
  passes (`data_directory_writable`, `ai_provider_configured`), `503`
  otherwise. Optional-capability checks (`ffmpeg_available`,
  `hachoir_available`, needed only for video processing) are reported but
  never block readiness — use this endpoint, not `/health`, for a
  load-balancer/orchestrator readiness probe if one is ever added.

## Frontend

**Start command**:

```bash
streamlit run frontend/app.py --server.port 8501
```

**Configuration**: set `BACKEND_URL` (env var, read via `.env`/`python-dotenv`)
to the backend's externally-reachable base URL, e.g.
`BACKEND_URL=https://api.example.com`. Locally this defaults to
`http://localhost:8000`.

The frontend has no persistence of its own and no server-side state beyond
Streamlit's own session state — it only talks to the backend over HTTP, so
it can be scaled/restarted independently of backend data durability
concerns.

## What's intentionally NOT here

Per S7 scope: no Docker (not currently necessary — both processes run
directly via their standard start commands above), no
Kubernetes/Terraform/cloud-specific IaC, no CI/CD deployment automation
(see `.github/workflows/` for the *test*-only CI added this phase), no
authentication, no TLS termination guidance (assumed to be handled by
whatever's in front of these two processes in a real deployment).

## Pre-deployment checklist (for whoever does P1)

- [ ] Durable volume/filesystem provisioned for `data_dir`
- [ ] `.env` populated for the target environment (never commit it)
- [ ] `MAX_UPLOAD_SIZE_MB` reviewed for real expected file sizes
- [ ] `GET /ready` returns `200` in the target environment
- [ ] Decide: keep `MockAIProvider`, or implement and wire a real provider
      (see `backend/app/services/ai_providers/base.py` for the interface)
- [ ] Decide: file-based storage acceptable for launch, or migrate to a
      database/object store first
- [ ] Authentication added if the deployment is not fully private
