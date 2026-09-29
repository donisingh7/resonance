# Resonance — Build Status

Last updated: 2026-09-29 (P1.2 — real OpenAI provider adapter, code-complete, not live-tested)

**S7 was the final planned main development phase.** P1 is the deployment
phase that follows it. P1.1 (baseline verification on `main`: clean tree,
19/19 pytest, evaluation harness PASS) is done. **P1.2, described below, adds
a real `OpenAIProvider` behind the existing `AIProvider` interface — the
code exists and is unit-tested with stubs, but no real OpenAI API key has
been used and no live API request has been made.** `MockAIProvider` remains
the default provider and this phase changes nothing about its behavior.

## P1.2 — Real OpenAI provider adapter

### What was added

- **Configuration** (`backend/app/core/config.py`, `.env.example`):
  `AI_PROVIDER` now also accepts `"openai"` (default remains `"mock"`).
  Three new settings, all `None` by default and all required together when
  `AI_PROVIDER=openai`: `OPENAI_API_KEY`, `OPENAI_TEXT_MODEL`,
  `OPENAI_TRANSCRIBE_MODEL`. Model names have **no hardcoded fallback**
  anywhere in business logic — they must come from `.env`, since model
  availability changes over time. `.env.example` contains commented
  placeholders/examples only, never a real key.
- **`backend/app/services/ai_providers/openai_provider.py`** —
  `OpenAIProvider`, implementing the same `AIProvider` interface as
  `MockAIProvider` (`transcribe_audio`, `analyze_image`,
  `synthesize_project`, `generate_questionnaire`) with **zero changes** to
  the public interface in `base.py`. Uses the official `openai` Python SDK
  (`openai==3.20.0`, added to `requirements.txt`):
  - **Audio** → `client.audio.transcriptions.create(model=OPENAI_TRANSCRIBE_MODEL, file=...)`.
  - **Image** → `client.responses.parse(model=OPENAI_TEXT_MODEL, input=[...with an input_image data URL...], text_format=<schema>)`,
    asking for OCR-like extracted text (nullable) and a concise visual
    description.
  - **Project synthesis** and **questionnaire generation** → the same
    `responses.parse(..., text_format=<schema>)` structured-output pattern,
    using schema-validated Pydantic models (defined locally in this module,
    not exported) instead of free-form JSON parsing — malformed output
    raises `OpenAIProviderError` rather than being guessed at or silently
    replaced with mock content.
  - **Evidence/related-theme integrity, defensively re-checked here**: every
    returned evidence item's `asset_id`/`processing_result_id`/
    `source_filename` must exactly match one of the asset contexts actually
    passed in, and its `excerpt` (if any) must be a real substring of that
    asset's own text — anything else is dropped (counted in
    `metadata.evidence_dropped_invalid_reference_count`), never "corrected."
    Same treatment for a generated question's `related_theme`: it's kept
    only if it's literal text from the supplied intelligence context,
    otherwise the question is dropped (counted in
    `metadata.questions_dropped_invalid_related_theme_count`). This is in
    addition to — not a replacement for — `intelligence.py`'s own existing
    (coarser) `processing_result_id` filter, which is unchanged.
  - **Token usage**: every metadata dict's `token_usage` is either the
    real dict the SDK returned (`response.usage.model_dump()` /
    `transcription.usage.model_dump()`) or `None` if the SDK didn't return
    one — never a fabricated number, preserving the convention established
    in S7 for `MockAIProvider`.
- **Configuration failure handling**: `OpenAIProvider.__init__` checks all
  three required settings and raises `OpenAIConfigurationError` (a
  `ValueError` subclass) naming exactly which are missing — by env var
  name only, never a value — if any are absent. This is deliberately a
  `ValueError` subclass so the **existing** `_check_ai_provider_configured()`
  in `readiness.py` (unchanged) catches it automatically.
- **Provider registry** (`ai_providers/__init__.py`): `_PROVIDERS` now maps
  `"mock" → MockAIProvider` and `"openai" → OpenAIProvider`. An unknown
  provider name still raises a clear `ValueError`. Registering the class
  does not instantiate it — `AI_PROVIDER=mock` never touches any OpenAI
  setting or imports the `openai` package's client beyond the class
  definition existing.
- **`/ready` behavior** (`backend/app/api/readiness.py`,
  `services/readiness.py` — **unchanged, no new code needed**): the
  existing `ai_provider_configured` check calls `get_ai_provider()`, which
  now naturally exercises `OpenAIProvider.__init__`'s validation. In
  `mock` mode, `/ready` is completely unaffected by OpenAI settings being
  unset (verified by test). In `openai` mode, `/ready` reports
  `ai_provider_configured: false` with the missing-config detail if
  `OPENAI_API_KEY` (etc.) is absent, or `true` once all three are set —
  **without making any network call**, since constructing
  `openai.OpenAI(api_key=...)` is local-only (verified interactively and
  covered by a test).
- **Tests** (`backend/tests/test_openai_provider.py`, 11 new tests, no
  real network calls anywhere): mock resolves with no OpenAI config;
  `AI_PROVIDER=openai` resolves `OpenAIProvider`; missing key raises a
  clear config error without leaking the (fake) key value; unknown
  provider name fails clearly; `/ready` in mock vs. openai mode (missing
  key → not ready; configured → ready, no network call); audio
  transcription response mapping; image analysis response mapping;
  project synthesis mapping **and** invalid-evidence dropping (asset not
  in context, excerpt not a real substring, mismatched filename — 3 bad
  items dropped, 1 valid item kept); questionnaire mapping **and**
  invalid-related-theme dropping; token usage is the real stubbed value or
  `None`, never fabricated. All provider-call tests stub
  `OpenAIProvider._client` directly with a local fake object after
  constructing the real client (proving construction itself is
  network-free) — no `openai` SDK method is ever actually invoked.

### What was explicitly NOT done this phase

- **No live OpenAI API request of any kind was made.** No real
  `OPENAI_API_KEY` was used anywhere, including in tests.
- No claim is made about real transcription/vision/synthesis/questionnaire
  quality — that requires an actual live smoke test, which is a distinct,
  deliberately separate next step (P1.3+), not part of P1.2.
- `MockAIProvider` was not modified, and remains the default in `.env.example`.
- No deployment, no database, no authentication — unchanged from S7.

### Verification (measured, this phase)

- `python -m pytest backend/tests -v` → **30 passed** (19 pre-existing +
  11 new `test_openai_provider.py` tests), 0 failed.
- `python scripts/evaluate.py` (mock mode, unaffected by this phase) →
  **Overall: PASS**, all 14 checks green (same harness, same fixtures, run
  fresh after this phase's changes to confirm nothing regressed).

## S1–S7 implementation (unchanged this phase)

Last updated for S7: 2026-09-28 (S7 / R6 — hardening, evaluation harness, observability, deployment readiness)

**S7 is the final planned main development phase.** All product features
(S1–S6) are intact and unchanged; that phase only hardened, instrumented,
tested, documented, and prepared the existing system — no new user-facing
functionality was added there. See "Code development status" at the end of
this document.

## Implemented

### 1. Input / file security hardening

- **Upload size limit**: `MAX_UPLOAD_SIZE_MB` (`.env`, default `25`).
  Enforced in `POST /projects/{id}/upload` by reading at most
  `max_bytes + 1` from the upload stream (never buffering an unbounded
  amount of attacker-controlled data) and returning `413` if exceeded.
- **Zero-byte rejection**: an empty upload returns `400` before ingestion
  runs.
- **Path traversal prevention**: every caller-supplied id
  (`project_id`, `asset_id`, `result_id`, `intelligence_id`,
  `questionnaire_id`, `report_id`) is validated in `storage.py` against
  `^[A-Za-z0-9_-]{1,128}$` before being used to build any filesystem path.
  An invalid id raises the *same* NotFound exception as a genuinely
  missing one (e.g. `storage.get_project("../../etc")` raises
  `ProjectNotFoundError`, not a filesystem error) — a client can't tell
  "malformed" from "doesn't exist," and there is no way for a crafted id
  to escape `data/projects/`. Every real id in the system is a `uuid4`/
  `uuid5` hex string, so this is not a functional restriction.
- **Filename safety**: unchanged from S1 — `storage.safe_stored_filename()`
  already derived the stored filename from `Path(original_filename).stem`
  (which discards any directory components) plus a random prefix; this
  phase added a regression test proving a traversal-shaped original
  filename produces a safe stored filename.
- **No absolute machine paths leaked**: `storage.redact_absolute_paths()`
  strips the repo's absolute path out of any exception text before it's
  persisted into a `ProcessingResult`/`ProjectIntelligence`/
  `Questionnaire`/`ExecutiveReport` `error` field or risk-flag message.
  Several parsing libraries (Pillow, pypdf, mutagen, hachoir) embed the
  absolute file path in their exception text, which would otherwise leak
  local filesystem/username layout through an ordinary API response.
- **Temp-file cleanup**: reviewed — video processing's `tmp_dir` was
  already wrapped in `try/finally: shutil.rmtree(..., ignore_errors=True)`
  (S3, unchanged); PDF report rendering writes directly to its final path
  via `reportlab`, no intermediate temp file exists to clean up.

### 2. Error / failure hardening

Reviewed every pipeline boundary (upload → ingestion → processing →
intelligence → questionnaire → report → PDF → workflow orchestration). One
real gap was found and fixed:

- **`report.py`'s `generate_report()`** previously only isolated PDF
  rendering failures — an unexpected error anywhere else in report
  construction (coverage/summary/risk-flag building) would have propagated
  as an unhandled exception. It now wraps the full report-building body in
  a try/except that produces a `status="failed"` `ExecutiveReport` (with a
  redacted error message) instead, mirroring the pattern already used by
  `processing.py`, `intelligence.py`, and `questionnaire.py`. This was a
  surgical addition, not a rewrite — the existing PDF-specific isolation
  is unchanged and still nested inside.
- Every other boundary already followed this pattern from S3–S6 and needed
  no change: a per-asset processing failure never blocks other assets or
  corrupts the project; a provider failure during intelligence/
  questionnaire generation is captured as a `status="failed"` record, not
  raised; workflow orchestration catches a per-asset exception inside its
  loop and continues.
- No raw stack trace is ever returned to a client: FastAPI's default
  handler already returns a generic 500 body without a traceback for any
  truly unexpected exception, and every *expected* failure mode above now
  produces a clean status + message instead of reaching that default
  handler at all.

### 3. Observability (`backend/app/core/observability.py`)

- `track_operation(operation, **fields)` — a context manager wrapped
  around every top-level service entrypoint that does real work:
  `processing.process_asset`, `intelligence.generate_project_intelligence`,
  `questionnaire.generate_questionnaire`, `report.generate_report`,
  `workflow.run_workflow`. Emits one structured JSON log line per call with
  a short correlation id (`operation_id`), the seeded fields
  (`project_id`, `asset_id`, `modality`, `provider`, etc.), `status`
  (defaults to `"completed"`, overridden by the caller to reflect the
  actual outcome — e.g. a caught per-modality failure still logs
  `status="failed"` even though no exception escaped), `duration_ms`, and
  — on an uncaught exception — `error_type`/`error_message`, before
  re-raising unchanged.
- An HTTP middleware in `main.py` does the same per-request: assigns a
  correlation id, echoes it via an `X-Request-ID` response header, and
  logs method/path/status/duration for every request.
- **Never logs** file contents, extracted text, transcripts, evidence
  excerpts, secrets, or API keys — only identifiers, status, timing, and
  short (300-char-capped) error summaries.
- Not an external monitoring integration — one structured `logging` line
  per event, greppable locally or pipeable into any aggregator later.

### 4. Processing / workflow metrics

Captured via the same `track_operation` calls above, plus fields already
persisted from S3–S6:
- Per processing operation: `modality`, `provider`, `status`,
  `duration_ms` (also already persisted per-result in
  `ProcessingResult.processing_metadata.duration_ms` since S3).
- Per intelligence run: `source_result_count`, `evidence_count`,
  `duration_ms`.
- Per questionnaire generation: `question_count`, `duration_ms`.
- Per report generation: `evidence_count`, `source_result_count`,
  `duration_ms`.
- Per workflow run: `total_assets`, `assets_processed`, `assets_failed`,
  `assets_skipped`, `stages_completed`, `stages_skipped`, `duration_ms`.
- **Token usage**: every `MockAIProvider` metadata dict now includes
  `"token_usage": None` — explicitly null because no real model call was
  made, never a fabricated number. A future real provider should populate
  the same key with an actual usage summary; see the convention documented
  at the top of `ai_providers/base.py`.

### 5. Readiness / capability endpoint

- **New: `GET /ready`** (`backend/app/api/readiness.py` +
  `services/readiness.py`) — returns a `ReadinessReport` with individual
  `ReadinessCheck`s: `data_directory_writable` and `ai_provider_configured`
  (both `required=True`, and `ready` reflects only these), plus
  `ffmpeg_available` and `hachoir_available` (both `required=False` —
  reported for visibility, never block readiness, since every other
  modality/feature keeps working without them). Returns HTTP `200` when
  `ready=True`, `503` otherwise. `GET /health` is unchanged (liveness
  only: "is the process up").

### 6. Reproducible evaluation harness (`evaluation/` + `scripts/evaluate.py`)

An **engineering/pipeline** evaluation, explicitly not an AI-quality
benchmark — see `evaluation/README.md`. Runs entirely in-process via
FastAPI's `TestClient` (no server/port needed) against a temporary,
disposable data directory (auto-cleaned afterward; never touches the real
`data/`). Uses only synthetic fixtures written for this project
(`evaluation/fixtures/*.txt`) plus a PNG generated in-memory via Pillow and
a deliberately corrupt "PDF" — no Bosch/client/third-party data.

Exercises: project create → upload (2 TXT + 1 generated PNG + 1 corrupt
PDF) → full workflow run → evidence integrity check → questionnaire edit →
second workflow run (idempotency + edit-preservation check) → report
fetch → PDF download. Emits a JSON result (also written under gitignored
`runtime/evaluation-results/`) and a human-readable summary, both
partitioned into:
- **Category A — measured local engineering metrics**: files attempted/
  ingested, processing success/failure counts, workflow completion state,
  evidence valid/invalid counts, idempotency result, questionnaire-edit
  preservation, report/PDF generation, total workflow latency, per-stage
  completion.
- **Category B — explicitly not yet measured**: semantic accuracy,
  transcription quality, vision quality, real LLM quality, production
  throughput, business ROI — each listed with a one-line reason (requires
  a real AI provider, not yet integrated).

**First real run result: 14/14 checks PASS** (see "Actual evaluation run
results" below).

### 7. Evidence integrity check (`backend/app/services/evidence_integrity.py`)

`check_evidence_integrity(project_id, intelligence_id=None)` verifies every
`EvidenceItem` on a `ProjectIntelligence` references a real `asset_id`, a
real `processing_result_id` that actually belongs to that asset, and that
asset's own `original_filename`. Returns a typed `EvidenceIntegrityReport`
(`total_evidence_items`, `valid_evidence_items`, `invalid_evidence_items`,
`all_valid`, and a list of `EvidenceIntegrityIssue`s with the specific
reason). **Never repairs or invents a replacement** for a bad reference —
only reports what it finds. Reuses the existing S4 `EvidenceItem`/
`ProjectIntelligence` shapes as-is; this is a validator, not a redesign.
Used by both `scripts/evaluate.py` and `backend/tests/test_critical.py`.

### 8. Critical regression tests (`backend/tests/`)

19 focused pytest tests (not a push for coverage — only the highest-risk
contracts): upload rejects unsupported type / oversize / empty file;
traversal-shaped filenames are sanitized; `stored_path` is never absolute;
unknown and malformed project ids both return `404` (never `500`); a
storage-layer test directly proves `../../../etc`-style ids raise
`ProjectNotFoundError` without creating anything outside the configured
data root; one project's asset is invisible via another project's id;
a corrupt-PDF processing failure doesn't block a sibling asset's success;
retry overwrites rather than duplicates a processing result; a full
workflow run is idempotent *and* preserves a manual questionnaire edit
across a second run, with no duplicate intelligence/questionnaire/report
records; evidence integrity passes for real generated intelligence and
correctly flags a deliberately tampered reference; report generation
produces a downloadable, valid-header PDF; project overview correctly
derives `not_started` for an empty project and `completed` after a full
run; the readiness endpoint reports the two required checks. Uses
`fastapi.testclient.TestClient` with a per-test throwaway `data_dir`
(`tmp_path` fixture) — no test ever touches real project data.

**Result: 19/19 PASS** (see below).

### 9. Repository hygiene

Practical grep/git checks performed (no heavyweight secret-scanning
toolchain):
- `git status` / `git ls-files` confirm `.env`, `data/`, `.venv/`, and the
  new `runtime/` (added to `.gitignore` this phase, for evaluation-result
  JSON output) are all correctly untracked.
- Grepped the whole tree (excluding `.venv`/`data`/`runtime`) for
  API-key/secret/password/token-shaped strings and common credential
  patterns (`sk-…`, AWS access-key shape, PEM private-key headers) —
  **no matches**.
- Grepped for "Bosch" / this machine's local username — the only matches
  are the project's own clean-room policy statements in `CLAUDE.md` and
  `evaluation/README.md` ("never introduce Bosch code/data"), which are
  intentional, not leaks.
- Grepped for this machine's absolute local path
  (`C:\Users\...\Downloads\Doni\Projects\resonance`) across tracked
  source/docs — **no matches**.
- No `.env` file exists in the working tree at all (only `.env.example`,
  which contains placeholders/comments, never a real value).

**Finding: repository hygiene is clean.** Nothing was removed or amended
as a result — see below for what a real secret-scanning setup would add
later if desired (out of scope for S7's "practical" pass).

### 10. Deployment readiness (`docs/DEPLOYMENT.md`)

Documentation only — **Resonance is not deployed anywhere**. Covers: exact
backend start command (`uvicorn app.main:app --app-dir backend --host 0.0.0.0
--port 8000`), the full environment-variable table (including the new
`MAX_UPLOAD_SIZE_MB`), the runtime storage assumption, `/health` vs. `/ready`
semantics, the exact Streamlit start command and `BACKEND_URL`
configuration, and — most importantly — an explicit, unambiguous statement
that **current persistence is local file-based storage and requires a
persistent filesystem/volume**; this repo must not be deployed to an
ephemeral/serverless filesystem and assumed durable. Ends with a
pre-deployment checklist for whoever does P1.

### 11. README.md finalization

Rewritten to code-complete/recruiter quality: what Resonance does, the
clean-room statement, a supported-modalities table (real vs.
AI-dependent processing per modality), a Mermaid architecture diagram, a
Mermaid end-to-end workflow diagram, an explanation of evidence
traceability as the project's core differentiator, idempotency guarantees,
exact local run / evaluation-harness / test commands, current limitations
(explicit mock-mode statement up front, not buried), and next production
steps. No fabricated accuracy numbers, ROI, or production-deployment
claims anywhere.

### 12. CI readiness (`.github/workflows/ci.yml`)

No CI existed before this phase. Added one minimal workflow: checkout,
`actions/setup-python` (3.12), `pip install -r requirements.txt`, run
`backend/tests/` via pytest, run `scripts/evaluate.py`. Triggers on push/PR
to `main`. No deployment automation, no secrets required, no frontend
build step (Streamlit needs none). This workflow has not been run on
GitHub yet (this machine can't push) — it mirrors exactly the commands
verified locally in this phase's critical verification pass.

## Current architecture

```
resonance/
├── backend/app/
│   ├── main.py                    # + readiness router, request-logging middleware
│   ├── api/
│   │   ├── health.py
│   │   ├── readiness.py           # GET /ready (S7)
│   │   ├── projects.py            # + upload size/empty-file enforcement (S7)
│   │   ├── assets.py
│   │   ├── processing_results.py
│   │   ├── intelligence.py
│   │   ├── questionnaires.py
│   │   ├── reports.py
│   │   ├── overview.py
│   │   └── workflow.py
│   ├── core/
│   │   ├── config.py              # + max_upload_size_mb
│   │   └── observability.py       # track_operation(), log_event() (S7)
│   ├── models/
│   │   ├── project.py / asset.py / processing.py
│   │   ├── intelligence.py / questionnaire.py / report.py
│   │   ├── overview.py / workflow.py
│   │   ├── readiness.py           # ReadinessReport, ReadinessCheck (S7)
│   │   └── evidence_integrity.py  # EvidenceIntegrityReport (S7)
│   └── services/
│       ├── storage.py             # + id validation, redact_absolute_paths (S7)
│       ├── ingestion.py           # + redacted error messages (S7)
│       ├── processing.py          # + track_operation, redacted errors (S7)
│       ├── intelligence.py        # + track_operation, redacted errors (S7)
│       ├── questionnaire.py       # + track_operation, redacted errors (S7)
│       ├── report.py              # + track_operation, full-body failure isolation (S7)
│       ├── report_pdf.py
│       ├── overview.py
│       ├── workflow.py            # + track_operation, metrics fields (S7)
│       ├── readiness.py           # capability/readiness checks (S7)
│       ├── evidence_integrity.py  # evidence-reference validator (S7)
│       ├── video_tools.py
│       └── ai_providers/          # + token_usage: null convention (S7)
│           ├── base.py
│           ├── mock_provider.py
│           ├── openai_provider.py # OpenAIProvider (P1.2, code-only, not live-tested)
│           └── __init__.py        # + "openai" registry entry (P1.2)
├── backend/tests/                 # pytest regression suite (S7) + P1.2
│   ├── conftest.py
│   ├── test_critical.py
│   └── test_openai_provider.py    # P1.2, no real network calls
├── evaluation/                    # evaluation harness fixtures + docs (S7)
│   ├── fixtures/*.txt
│   └── README.md
├── scripts/evaluate.py            # evaluation harness entrypoint (S7)
├── .github/workflows/ci.yml       # test-only CI (S7)
├── frontend/app.py
├── data/                          # gitignored, runtime
├── runtime/                       # gitignored, runtime (S7: evaluation-results/)
├── requirements.txt                # + pytest, httpx (S7)
├── .env.example                   # + MAX_UPLOAD_SIZE_MB (S7)
├── CLAUDE.md
├── README.md                       # rewritten (S7)
└── docs/
    ├── BUILD_STATUS.md
    └── DEPLOYMENT.md               # new (S7)
```

## Known limitations

- **All AI-derived content remains `MockAIProvider` deterministic
  placeholder output** — S7 added zero new AI content; it hardened and
  instrumented what S3–S6 already produce. This is the single most
  important thing to communicate about this project's current state, and
  it's now stated in the first paragraph of `README.md`, not buried.
- Security hardening this phase was **pragmatic, not exhaustive**: id
  validation, upload limits, path-safety, and error-message redaction were
  addressed because they were concretely reachable through this app's
  actual attack surface (path-built-from-user-id, unbounded upload,
  leaked absolute paths). Not covered, and explicitly deferred: rate
  limiting, authentication/authorization, CSRF (irrelevant without
  cookies/sessions today), dependency vulnerability scanning, and a
  proper secret-scanning toolchain in CI.
- Observability is structured `logging` to stdout, not an external
  monitoring/tracing integration (no OpenTelemetry, no log aggregator
  wiring) — intentionally, per S7 scope.
- The evaluation harness measures pipeline/engineering correctness only;
  it cannot and does not measure whether `MockAIProvider`'s output is
  "good" in any semantic sense, because there is no real model to judge.
- The pytest suite is intentionally small (19 tests) and will not catch
  every possible regression — it targets the specific high-risk contracts
  enumerated in S7's scope, not general coverage.
- `docs/DEPLOYMENT.md` is preparation, not a deployment — this app has
  never run outside a local developer machine.
- Persistence is still file-based (no database) and still assumes a
  durable local filesystem — unchanged from S1–S6, now explicitly flagged
  as a hosting constraint in `docs/DEPLOYMENT.md`.
- No authentication, no multi-user support, no cloud deployment.

## Actual evaluation run results (measured, this phase)

Ran once via `.venv\Scripts\python.exe scripts\evaluate.py`:

```
files_attempted: 4          files_ingested_successfully: 4
processing_success_count: 3  processing_failure_count: 1
workflow_completion_state: completed
total_workflow_latency_ms: 157.0
evidence_total: 19           evidence_valid: 19    evidence_invalid: 0
pdf_size_bytes: 9148
```

All 14 checks: **PASS**. This is a **Category A (measured engineering
metric)** result — it says nothing about AI output quality (Category B,
not yet measured; see `evaluation/README.md`).

## Critical test results (measured, this phase)

`.venv\Scripts\python.exe -m pytest backend/tests -v` → **19 passed** in
~2.7s. Two pre-existing, unrelated deprecation warnings (Starlette's
`anyio.abc.BlockingPortal` alias, pydantic-settings' class-based `Config`)
— cosmetic, not addressed, per S7's "don't chase cosmetic warnings" scope.

## Code development status

**Code development for the main phases (S1–S7) is complete.** Every phase
from foundation (S1) through hardening/evaluation/deployment-readiness
(S7) has been implemented, smoke- or test-verified, and documented. P1 (the
deployment phase) is now in progress: P1.1 (baseline verification) and
P1.2 (real OpenAI provider adapter, code-complete but not live-tested — see
above) are both done. See `CLAUDE.md`'s "High-level future phases" for the
exact list.

## Next phase (not started)

A **live credential smoke test** of `OpenAIProvider` (P1.3+) — running it
against a real `OPENAI_API_KEY` for the first time — has deliberately not
been done yet and is the natural next step before any claim about real AI
quality can be made. Beyond that: a persistent database/object-storage
backend, authentication, cloud deployment, embeddings/vector DB, RAG,
Kubernetes/Terraform, elaborate monitoring — all still deliberately
deferred.
