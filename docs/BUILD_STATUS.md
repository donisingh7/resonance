# Resonance — Build Status

Last updated: 2026-09-28 (S4 / R3 — unified cross-asset intelligence + evidence traceability, mock provider)

## Implemented

**Backend (FastAPI, `backend/app/`)**
- `GET /health`
- `POST /projects`, `GET /projects/{project_id}`
- `POST /projects/{project_id}/upload` — ingests into an `Asset` (unchanged from S2)
- `GET /projects/{project_id}/assets`, `GET /projects/{project_id}/assets/{asset_id}`
- `POST /projects/{project_id}/assets/{asset_id}/process` — processes one
  asset per its modality and returns a `ProcessingResult` (unchanged from S3)
- `GET /projects/{project_id}/processing-results`, `GET .../processing-results/{result_id}`
- **New: `POST /projects/{project_id}/intelligence`** — generates
  project-level intelligence across all of that project's *completed*
  `ProcessingResult`s. Optional JSON body `{"provider": "mock"}` to override
  the default provider; body may be omitted/empty. Re-running this for the
  same project/provider overwrites the previous result rather than creating
  a duplicate (deterministic `uuid5(project_id, provider_name)` id) — the
  same idempotency strategy as asset processing, applied one level up.
- **New: `GET /projects/{project_id}/intelligence`** — lists all generated
  intelligence results for a project, sorted by `created_at`.
- **New: `GET /projects/{project_id}/intelligence/{intelligence_id}`**

**ProjectIntelligence model (`backend/app/models/intelligence.py`)**
`id, project_id, status (completed|failed), provider, created_at,
source_result_ids, summary, top_themes, sentiment_summary, pain_points,
positive_signals, questions_or_concerns, opportunities,
recommended_actions, evidence, processing_metadata, error`.
`source_result_ids` lists exactly the `ProcessingResult` ids whose content
fed the synthesis (i.e. completed results with non-empty extracted
text/transcript/visual description). `processing_metadata` records
transparency counts: total/completed processing results considered, ids of
failed results, ids of completed-but-empty-content results, whether the
per-project asset cap was hit, plus whatever metadata the provider itself
returns (e.g. `mock: true`, `asset_count`, `total_input_characters`).

**EvidenceItem model** — `category, statement, asset_id,
processing_result_id, source_filename, excerpt`. Every evidence item
returned by a provider is validated against the actual source-result ids
used for that generation before being persisted; anything that doesn't
match a real id in the input set is dropped rather than trusted. No
evidence is ever fabricated: `excerpt`, when present, is always a verbatim
substring of the corresponding asset's own processed text.

**AI provider abstraction (`backend/app/services/ai_providers/`)** — extended for S4:
- `base.py` — `AIProvider` interface gains `synthesize_project(assets:
  list[ProjectAssetContext]) -> ProjectSynthesisResult`, alongside the
  existing `transcribe_audio`/`analyze_image`. `ProjectAssetContext` is one
  asset's bounded text plus its ids/filename/modality; `ProjectEvidenceItem`
  and `ProjectSynthesisResult` define the structured synthesis + evidence
  shape every provider (mock or future real) must return.
- `mock_provider.py` — `MockAIProvider.synthesize_project()` is a
  **deterministic, keyword-heuristic** synthesis: word-frequency counting
  (minus a stopword list that also filters the mock provider's own
  transcript/description boilerplate) for `top_themes`; fixed pain/positive
  keyword lists for `pain_points`/`positive_signals`; sentence-level `?`
  detection for `questions_or_concerns`; templated `opportunities` and
  `recommended_actions` derived from the above. Every generated item that
  cites content is paired with a real excerpt found via substring search in
  the actual asset text — nothing is invented. All output is clearly
  labeled `[mock ...]` / `[mock sentiment]` / `[mock project synthesis]`,
  and is explicitly **not** real AI analysis — it exists to verify the
  end-to-end architecture, not to produce a good-quality reading of content.
- `__init__.py` — unchanged factory; no new provider implemented this phase.

**Cross-asset consolidation service (`backend/app/services/intelligence.py`, S4)**
`generate_project_intelligence(project_id, provider_name=None)`:
1. Loads the project's `ProcessingResult`s; splits into completed / failed.
2. Builds a bounded per-asset text context from completed results only:
   `transcript` + `extracted_text` + `visual_description` joined, truncated
   to 4000 chars/asset, capped at 50 assets total (`MAX_CHARS_PER_ASSET`,
   `MAX_ASSETS_IN_CONTEXT` in `intelligence.py`). Completed results with no
   usable text (e.g. a video with no audio and no meaningful frame text) are
   skipped and recorded in `processing_metadata.empty_content_result_ids`,
   not silently dropped.
3. If no asset yields usable context (no processed assets yet, or a project
   with only failed/empty results), returns a `status="completed"`
   `ProjectIntelligence` with an explanatory `summary` and empty
   lists/evidence, rather than erroring — a project with nothing processed
   yet is a normal state, not a failure.
4. Otherwise calls `provider.synthesize_project(contexts)`, validates
   returned evidence against the real context ids, and persists the result.
   A provider exception here is caught and turned into a `status="failed"`
   `ProjectIntelligence` with an `error` message — mirrors how
   `processing.py` handles a per-asset provider failure — so one bad
   generation never corrupts the project or a prior successful result.

**Persistence** — extended: `data/projects/{project_id}/intelligence/{intelligence_id}.json`
alongside the existing `project.json`, `uploads/`, `assets/`,
`processing_results/`. `storage.py` now explicitly opens all JSON files
with `encoding="utf-8"` (previously relied on the OS default, which is
`cp1252` on Windows and cannot represent characters like `→` that can
appear in generated summary text — this was a latent cross-platform bug,
fixed as part of this phase since S4 output was the first content to
trigger it).

**Frontend (Streamlit, `frontend/app.py`)**
- Unchanged: health check, create/load project, multi-file upload, asset
  list with per-asset "Process asset" and result display.
- **New "Project intelligence" section** on the active project page:
  - Shows asset count and how many have a completed processing result.
  - **"Generate Project Intelligence"** button (calls `POST .../intelligence`).
  - Lists all generated intelligence records (newest first, latest
    expanded), each showing: a "MockAIProvider output ... not real AI
    analysis" caption when `provider == "mock"`, summary, top themes, pain
    points, opportunities, sentiment summary, positive signals, recommended
    actions, questions/concerns, and every evidence item (category,
    statement, source filename, asset/result id, excerpt) plus the list of
    source processing-result ids.
  - A `status == "failed"` record shows its `error` instead of empty
    sections.

## Current architecture

```
resonance/
├── backend/app/
│   ├── main.py                    # + intelligence router
│   ├── api/
│   │   ├── health.py
│   │   ├── projects.py
│   │   ├── assets.py              # + POST /assets/{id}/process
│   │   ├── processing_results.py  # GET list + GET by id
│   │   └── intelligence.py        # POST / GET list / GET by id (S4)
│   ├── core/config.py             # ai_provider, ai_api_key settings (unchanged)
│   ├── models/
│   │   ├── project.py
│   │   ├── asset.py
│   │   ├── processing.py          # ProcessingResult, ProcessingStatus
│   │   └── intelligence.py        # ProjectIntelligence, EvidenceItem (S4)
│   └── services/
│       ├── storage.py             # + intelligence persistence, utf-8 everywhere
│       ├── ingestion.py
│       ├── processing.py          # per-modality orchestration (S3)
│       ├── intelligence.py        # cross-asset consolidation service (S4)
│       ├── video_tools.py         # ffmpeg/ffprobe subprocess wrappers
│       └── ai_providers/
│           ├── base.py            # + ProjectAssetContext/Result, synthesize_project
│           ├── mock_provider.py   # + synthesize_project() keyword heuristic
│           └── __init__.py        # get_ai_provider() factory
├── frontend/app.py                # + "Project intelligence" section
├── data/                          # gitignored, runtime (includes data/tmp/)
├── requirements.txt
├── .env.example
├── CLAUDE.md
└── docs/BUILD_STATUS.md
```

## Known limitations

- **All project intelligence output from `MockAIProvider` is deterministic,
  keyword-heuristic placeholder synthesis, not real AI analysis.** Themes
  come from word-frequency counting, sentiment/pain/positive signals from
  fixed keyword lists, and questions from `?` detection — not an LLM. This
  is by design for this phase (architecture/flow verification), not an
  oversight, and every mock output is clearly labeled as such.
- Mock synthesis quality is intentionally not tuned further: audio/image/
  video assets still only contribute `MockAIProvider`'s placeholder
  transcript/description text (from S3), so real signal in this phase comes
  primarily from PDF/TXT documents' genuinely extracted text.
- The per-project synthesis context is bounded (4000 chars/asset, 50 assets
  max) for predictability; a project exceeding the asset cap has
  `processing_metadata.asset_context_capped = true` and only its first 50
  completed results (by creation order) are considered.
- `list_project_intelligence` / `list_processing_results` / `list_assets`
  read every file per request — fine at current scale, same trade-off noted
  in S3.
- No questionnaire generation, executive/PDF report, embeddings, vector
  search, or RAG yet — deliberately deferred from this phase.
- No authentication, no database, no queues, no containerization/deployment.
- No automated test suite — verified via one manual smoke pass (see below).

## Smoke-tested this phase

Backend started locally (isolated virtualenv); full flow exercised via
scripted HTTP calls against a running instance:
- A project with two uploaded/processed TXT assets → generated project
  intelligence: `status="completed"`, `source_result_ids` has both results,
  evidence present, every evidence item's `asset_id`/`processing_result_id`
  matches a real uploaded asset/result and `source_filename` matches the
  real uploaded filename.
- A project with **no** processing results → intelligence generation
  returns `status="completed"` with an explanatory empty summary, not an
  error.
- A project with a **mixture** of one completed TXT result and one failed
  (deliberately corrupt "PDF") result → intelligence generation succeeds,
  uses only the completed result's content, and records the failed result's
  id in `processing_metadata.failed_result_ids` while excluding it from
  `source_result_ids`.
- `GET` by id and `GET` list both verified against a generated record.
- **Idempotency**: regenerating intelligence for the same project (default
  provider) returns the same `id` and the list endpoint still shows exactly
  one record — no duplicate accumulation.
- 404s verified for an unknown project and an unknown intelligence id.
- Re-verified unaffected: health check, project create/get, upload,
  asset list/get, asset processing (TXT/PDF), processing-result list/get —
  all still return 200 with expected shapes.
- Streamlit booted successfully against the smoke-test backend and served
  its page with no server-side exceptions in the log.
- Not re-tested this phase: audio/image/video asset processing (S3
  functionality, unchanged code path) — the local dev machine's corporate
  package mirror couldn't resolve the pinned `hachoir` version needed for
  video metadata, an environment/dependency-mirror limitation unrelated to
  the S4 code changes, not a regression.

## Next phase (not started)

Questionnaire generation, executive PDF report, final management report.
Also not started: embeddings/vector database, RAG/semantic search, database
migration, authentication, cloud deployment, queues, large UI redesign.
