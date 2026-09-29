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
  - `api/` — route modules (one file per resource: `health.py`, `readiness.py`, `projects.py`, `assets.py`)
  - `core/` — settings/config (`config.py`, pydantic-settings, reads `.env`) and
    `observability.py` (S7 — structured operation logging, see below)
  - `models/` — pydantic models (data shapes, not ORM — no DB yet): `project.py` (Project),
    `asset.py` (Asset, Modality, IngestionStatus, MODALITY_BY_EXTENSION — the single
    source of truth for which extensions are supported and their modality),
    `intelligence.py` (ProjectIntelligence, EvidenceItem, IntelligenceStatus —
    the S4 cross-asset synthesis result and its evidence trail),
    `questionnaire.py` (Questionnaire, Question, QuestionType — the S5
    follow-up questionnaire derived from a ProjectIntelligence), `report.py`
    (ExecutiveReport, RiskFlag, RiskSeverity, QuestionnaireSummary — the S5
    management-readable report, reusing `EvidenceItem` from `intelligence.py`),
    `overview.py` (ProjectOverview, StageStatus — the S6 read-only pipeline
    snapshot for one project), `workflow.py` (WorkflowRunResult — the S6
    orchestration run outcome, reusing `ProjectOverview`), `readiness.py`
    (ReadinessReport, ReadinessCheck — the S7 capability/readiness snapshot),
    `evidence_integrity.py` (EvidenceIntegrityReport, EvidenceIntegrityIssue
    — the S7 evidence-reference validator's typed result)
  - `services/` — business logic / persistence:
    - `storage.py` — file-based persistence only (projects, assets,
      processing results, project intelligence, questionnaires, reports on
      disk). Owns the on-disk layout; no metadata extraction or AI logic
      here. **Every caller-supplied id (`project_id`, `asset_id`,
      `result_id`, `intelligence_id`, `questionnaire_id`, `report_id`) is
      validated against a strict `^[A-Za-z0-9_-]{1,128}$` pattern before
      being used to build a filesystem path** (S7 hardening) — an invalid
      id raises the same NotFound exception as a missing one, so a client
      can't distinguish "malformed" from "doesn't exist" and path
      traversal via a crafted id is structurally impossible. Also owns
      `redact_absolute_paths()`, used everywhere an exception's `str(exc)`
      is persisted into an `error` field or risk-flag message, since some
      parsing libraries embed the absolute file path in their error text.
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
      `status="failed"` result, mirroring `processing.py`. Also exposes
      `resolve_intelligence(project_id, intelligence_id)` — looks up a
      specific intelligence result or the most recently generated one —
      shared by `questionnaire.py` and `report.py` (S5) so both build on
      the same resolution rule. All API-facing logic for this phase lives
      here, not in `api/intelligence.py`.
    - `questionnaire.py` — the follow-up questionnaire service (S5). Resolves
      a `ProjectIntelligence` (specific or latest), calls
      `provider.generate_questionnaire()` with only that intelligence's
      already-generated fields (never re-reads raw asset text), and persists
      a `Questionnaire`. Also owns `update_questionnaire()` for manual edits
      (replaces the `questions` list, preserves `created_at`, bumps
      `updated_at`).
    - `report.py` — the executive report service (S5). Resolves the target
      `ProjectIntelligence` and, if present, its `Questionnaire`; copies
      their fields verbatim into an `ExecutiveReport` (so evidence
      traceability carries over unchanged); computes deterministic,
      rule-based `RiskFlag`s from real pipeline state (never a
      content-moderation/safety classifier — see below); and attempts PDF
      rendering via `report_pdf.py`, isolating a rendering failure to a risk
      flag rather than failing the whole report.
    - `report_pdf.py` — renders an `ExecutiveReport` to PDF using `reportlab`
      (platypus). Every dynamic string is XML-escaped before being embedded
      in a `Paragraph`, since reportlab's Paragraph markup is a small XML
      dialect that would otherwise raise on real content containing
      `&`/`<`/`>`.
    - `overview.py` — the pipeline-state aggregation service (S6). Reads
      only already-persisted data (assets, processing results, intelligence,
      questionnaires, reports) and derives a `ProjectOverview`: counts,
      availability flags, and a deterministic `current_stage` /
      `overall_pipeline_status` / `next_recommended_action` cascade. No
      progress percentage is ever computed — status is always a discrete
      stage derived from what exists. Also exposes
      `intelligence_is_outdated()`, shared with `workflow.py` to detect when
      new processing results exist that the current intelligence doesn't
      cover yet.
    - `workflow.py` — the synchronous orchestration service (S6). Calls
      `processing.process_asset()` for every asset with no processing
      attempt yet, then `intelligence.generate_project_intelligence()` only
      if missing/failed/outdated, then `questionnaire.generate_questionnaire()`
      only if none exists yet for the current intelligence (never
      regenerates an existing one — that would silently discard manual
      edits), then `report.generate_report()` only if none exists yet for
      the current (intelligence, questionnaire) pairing. Pure composition
      of existing services — no new processing/synthesis logic, no queues,
      no background workers; it's one synchronous function call per run.
    - `video_tools.py` — thin ffmpeg/ffprobe subprocess wrappers (probe
      duration, extract audio, extract keyframes). No AI, no persistence.
    - `ai_providers/` — provider abstraction: `base.py` (the `AIProvider`
      interface: `transcribe_audio`, `analyze_image`, `synthesize_project`
      (S4), and — since S5 — `generate_questionnaire` for follow-up
      questions), `mock_provider.py` (deterministic default, no external
      calls), `openai_provider.py` (P1.2 — real OpenAI-backed adapter, see
      below), `__init__.py` (`get_ai_provider()` factory: `"mock"` →
      `MockAIProvider`, `"openai"` → `OpenAIProvider`, provider selected via
      `settings.ai_provider`; an unknown name raises `ValueError`). Add
      another real provider the same way — a new module here, registered in
      the factory; don't touch `processing.py`'s, `intelligence.py`'s, or
      `questionnaire.py`'s dispatch logic to add one. Every metadata dict
      returned here includes a `token_usage` key: `None` for
      `MockAIProvider` (it makes no real model call), and for
      `OpenAIProvider` either the real SDK-reported usage dict or `None` if
      the API didn't return one — never a fabricated number either way.
    - `openai_provider.py` (P1.2) — `OpenAIProvider`, the first real
      `AIProvider` implementation. **Code exists; no real credential/live
      smoke test has been run against it yet** — see
      `docs/BUILD_STATUS.md`. Only instantiated when `AI_PROVIDER=openai`;
      its `__init__` validates `OPENAI_API_KEY`/`OPENAI_TEXT_MODEL`/
      `OPENAI_TRANSCRIBE_MODEL` are set and raises `OpenAIConfigurationError`
      (a `ValueError` subclass, so the existing readiness check catches it
      with no changes needed there) if any are missing — model names are
      never hardcoded as a fallback in business logic, since availability
      changes over time. Uses the SDK's `responses.parse(...,
      text_format=<pydantic model>)` structured-output parsing (schemas
      internal to this module — `base.py`'s public TypedDict contract is
      unchanged) rather than free-form JSON parsing, so malformed output
      raises `OpenAIProviderError` instead of being guessed at. Defensively
      re-validates every returned evidence item (`asset_id`/
      `processing_result_id`/`source_filename` must exactly match a
      supplied context entry, `excerpt` must be a real substring of that
      asset's text) and every question's `related_theme` (must be literal
      text from the supplied intelligence) — invalid ones are dropped, never
      "corrected," before the result reaches `intelligence.py`/
      `questionnaire.py`'s own (coarser) existing filters. Constructing the
      SDK client (`OpenAI(api_key=...)`) makes no network call, so this is
      also what `/ready` uses to validate config in `openai` mode without
      spending a real API call.
    - `readiness.py` — the capability/readiness service (S7). Runs a small,
      fixed set of local checks (data directory writable, configured AI
      provider resolves, ffmpeg/hachoir importable) and reports them as a
      structured `ReadinessReport`. Only `required` checks affect the
      overall `ready` flag — an unavailable *optional* modality dependency
      (ffmpeg, hachoir) is surfaced for visibility but never marks the
      whole app unready, since every other modality/feature keeps working.
    - `evidence_integrity.py` — the evidence-reference validator (S7).
      Checks that every `EvidenceItem` on a `ProjectIntelligence` really
      references a real `asset_id`, a real `processing_result_id` that
      belongs to that asset, and that asset's own filename. Reports
      mismatches; never repairs or invents a replacement. Used by
      `scripts/evaluate.py` and `backend/tests/test_critical.py` — this is
      the S4 evidence architecture's own integrity check, not a redesign
      of it.
- **Observability** (S7, `core/observability.py`): `track_operation(name,
  **fields)` is a context manager wrapped around every top-level service
  entrypoint that does real work (`process_asset`,
  `generate_project_intelligence`, `generate_questionnaire`,
  `generate_report`, `run_workflow`) — it emits one structured JSON log
  line per call with a short correlation id, the passed fields
  (`project_id`, `asset_id`, `provider`, etc.), `status`, `duration_ms`,
  and — on an uncaught exception — `error_type`/`error_message`, then
  re-raises unchanged. A separate HTTP middleware in `main.py` does the
  same per-request (method, path, status code, duration) and echoes the
  correlation id back via an `X-Request-ID` response header. **Never log
  file contents, extracted text, transcripts, evidence excerpts, secrets,
  or API keys** — only identifiers, status, timing, and short error
  summaries; keep new instrumentation to that same discipline.
- **Frontend**: Streamlit, single `frontend/app.py` for now. Talks to backend
  only via HTTP (`BACKEND_URL` env var), no direct imports from `backend/`.
  Since S6, structured as a project picker (create/select/open-by-id, backed
  by `GET /projects`) followed by six tabs for the active project (Overview,
  Assets, Intelligence, Questionnaire, Executive Report, Evidence). All
  backend calls go through `api_get`/`api_post`/`api_put` helpers that
  return `None` on a connection failure so every call site can render a
  user-facing message via `show_backend_error()` instead of a raw
  stack trace — keep using these helpers for new frontend code rather than
  calling `requests` directly.
- **Persistence**: lightweight file-based, under `data/projects/{project_id}/`.
  No database yet. Each project has `project.json`, an `uploads/` subdirectory
  (raw stored files), an `assets/` subdirectory (one `{asset_id}.json` per
  ingested asset), a `processing_results/` subdirectory (one
  `{result_id}.json` per processed asset), an `intelligence/` subdirectory
  (one `{intelligence_id}.json` per generated project intelligence result),
  a `questionnaires/` subdirectory (one `{questionnaire_id}.json` per
  generated/edited questionnaire), and a `reports/` subdirectory (one
  `{report_id}.json` plus, when PDF rendering succeeds, a sibling
  `{report_id}.pdf`). `data/tmp/` holds transient per-run scratch space
  (e.g. video keyframe/audio extraction); always clean it up in a `finally`
  block after use. `data/` is gitignored (runtime data, not source) — this
  includes generated report PDFs, which are runtime artifacts, not source.
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
- **Questionnaire ids are deterministic**: `uuid5` of `(intelligence_id,
  provider_name)`. Regenerating a questionnaire for the same intelligence
  result/provider overwrites the previous questionnaire — **including any
  manual edits made via `PUT`** — same idempotency strategy, applied one
  level up again. This is documented, known behavior, not a bug: generate
  once, then edit; don't regenerate after editing unless you intend to
  discard the edits. Editing itself (`PUT`) is not idempotent-by-id in this
  sense — it always applies, preserving `created_at` and bumping `updated_at`.
- **Report ids are deterministic**: `uuid5` of `intelligence_id` alone (no
  provider — a report's `provider` field is copied from its source
  intelligence, since a report doesn't call an AI provider itself, it only
  reformats already-generated intelligence/questionnaire content).
  Regenerating a report for the same intelligence result overwrites the
  previous one (and its PDF file) rather than accumulating duplicates.
- **Workflow runs (S6) are idempotent by construction, not by id**: there is
  no `WorkflowRunResult` persistence — each run is a live composition of
  the same idempotent per-resource operations above (`process_asset`,
  `generate_project_intelligence`, `generate_questionnaire`,
  `generate_report`), each of which already no-ops or overwrites-in-place
  rather than duplicating. `workflow.py` additionally *skips* calling
  `generate_questionnaire`/`generate_report` at all once a current one
  exists (rather than relying solely on their own overwrite behavior),
  specifically so a second "Run Remaining Pipeline" click can never
  silently discard a manually edited questionnaire.
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
- AI processing (S3), cross-asset intelligence (S4), and questionnaire
  generation (S5): all provider-abstracted (`ai_providers/`); `MockAIProvider`
  is the default provider — deterministic, no external calls or credentials
  required. `OpenAIProvider` (P1.2, `openai` Python SDK) is a second,
  real implementation, selected via `AI_PROVIDER=openai` plus
  `OPENAI_API_KEY`/`OPENAI_TEXT_MODEL`/`OPENAI_TRANSCRIBE_MODEL` — code
  exists and is unit-tested with stubs, but **no live credential/API smoke
  test has been run against it yet**. ffmpeg/ffprobe (system binaries, not
  pip packages) used for video audio/keyframe extraction.
- PDF rendering (S5): `reportlab` (platypus), pure-Python, no system
  dependency. Used only to render an already-built `ExecutiveReport` to
  PDF — it has no role in generating report content.
- Testing/evaluation (S7): `pytest` + `httpx` (for FastAPI's
  `TestClient`) — both installed into `.venv` only, added to
  `requirements.txt`. `backend/tests/` is the regression suite;
  `scripts/evaluate.py` is the standalone evaluation harness, both driven
  through `TestClient` (in-process, no server/port needed) against a
  throwaway `data_dir` so neither ever touches real project data.
- No auth, no cloud deployment yet — see `docs/DEPLOYMENT.md` for what's
  documented-but-not-done to prepare for that.

## Coding rules

- Keep it simple; don't add abstractions, DB layers, or infra ahead of need.
- AI-dependent operations (transcription, vision, synthesis, questionnaire
  generation) go through the `ai_providers` abstraction and default to
  `MockAIProvider`. `OpenAIProvider` (P1.2) exists behind the same
  interface but must never be made the default, instantiated implicitly, or
  called with a real credential outside an explicit, deliberate live smoke
  test — do not add a third provider or extend the interface further until
  explicitly scoped.
- Processing (S3) is per-asset only; cross-asset synthesis (S4) and
  questionnaire/report generation (S5) are separate service layers on top
  of it, not folded into `processing.py`. Do not add embeddings, vector
  search, RAG, final management reports, or evaluation benchmarks until
  explicitly scoped.
- Cross-asset intelligence (S4) evidence must never be invented: every
  `EvidenceItem` persisted must reference a real `asset_id` /
  `processing_result_id` that was actually part of the synthesis input, and
  any `excerpt` must be a genuine substring of that asset's own processed
  text. `intelligence.py` defensively drops any evidence a provider returns
  that doesn't reference an id from the input context. Reports (S5) carry
  this same evidence forward verbatim — never regenerate or reinterpret it.
- Questionnaire generation (S5) must not invent new signals either: a
  generated `Question.related_theme`, when set, must be literal text that
  already appears in the source `ProjectIntelligence` (a theme, pain point,
  concern, opportunity, or the sentiment summary) — never a paraphrase or a
  bare category label. A questionnaire is a reformulation of existing
  intelligence output into follow-up prompts, not a new analysis pass.
- Risk/moderation flags (S5, `report.py`) are deterministic, rule-based
  pipeline/data-quality checks only (processing failures, excluded/empty
  assets, low source coverage, missing evidence, mock-provider output) —
  **not** a content-moderation or safety classifier. Do not add a keyword-
  based "safety" rule without labeling exactly how conservative/limited it
  is; none is implemented as of S5.
- Orchestration (S6, `workflow.py`) is a plain synchronous function that
  composes existing per-resource services — it must never contain its own
  processing/synthesis logic, and must never be turned into a queue,
  background worker, or async task system until explicitly scoped. If a
  new pipeline step is added later, wire it into `workflow.py`'s sequence
  and `overview.py`'s stage cascade together, so the "what's next" status
  and the "do what's next" action never drift apart.
- Pipeline status (S6, `overview.py`) is always a discrete, deterministically
  derived stage (`StageStatus`) — never a fabricated progress percentage or
  a value not directly traceable to persisted data.
- No authentication, Docker, queues, or cloud deployment until explicitly
  scoped.
- Validate inputs at API boundaries: file extension allowlist, upload size
  (`settings.max_upload_size_mb`, enforced in `api/projects.py`, `413` if
  exceeded), rejected zero-byte uploads (`400`), and every caller-supplied
  id validated against `storage._SAFE_ID_PATTERN` before touching the
  filesystem (S7). Trust internal service code otherwise.
- Never let an exception's raw `str(exc)` reach a persisted `error` field
  or an API response without passing it through
  `storage.redact_absolute_paths()` first — several parsing libraries
  (Pillow, pypdf, mutagen, hachoir) embed the absolute file path in their
  error text, which would otherwise leak local machine/filesystem layout.
- The regression suite in `backend/tests/` (pytest) covers only the
  highest-risk contracts explicitly scoped in S7 (upload validation, path
  safety, project isolation, failure isolation, idempotency, evidence
  integrity, questionnaire-edit preservation, report/PDF generation,
  overview stage behavior) — it is deliberately small. Do not chase a
  coverage percentage; add a test here only for a comparably high-risk
  contract, not for its own sake.
- `scripts/evaluate.py` is an **engineering/pipeline** evaluation harness,
  not an AI-quality benchmark — it must never claim or imply a semantic-
  accuracy/quality result for `MockAIProvider` output. Keep its
  "Category A: measured" vs. "Category B: not yet measured" separation
  whenever it's extended.
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
4. ~~Questionnaire generation + executive reporting + risk flags~~ —
   **done, mock-only** (S5/R4): a `Questionnaire` of follow-up questions is
   generated from a `ProjectIntelligence` and is user-editable; an
   `ExecutiveReport` packages that intelligence (plus the questionnaire, if
   any) into management-readable sections with deterministic risk/
   data-quality flags and, when `reportlab` is available, a downloadable
   PDF. Still mock-only — see `docs/BUILD_STATUS.md` for exact scope.
5. ~~Recruiter-ready end-to-end dashboard + workflow orchestration~~ —
   **done, mock-only** (S6/R5): a `ProjectOverview` aggregates real pipeline
   state (asset/processing counts, intelligence/questionnaire/report
   availability) into a deterministic stage and next-action; a synchronous
   `workflow.run` endpoint executes whichever pipeline steps are missing in
   one call, safely skipping steps that already exist (preserving manual
   questionnaire edits); a per-asset retry endpoint reuses `process_asset`
   unchanged; Streamlit was reorganized into a project picker + six tabs
   (Overview, Assets, Intelligence, Questionnaire, Executive Report,
   Evidence) as one coherent guided flow instead of disconnected controls.
   Still mock-only — see `docs/BUILD_STATUS.md` for exact scope.
6. ~~Hardening + evaluation harness + observability + deployment
   readiness~~ — **done, mock-only** (S7/R6): path-traversal-safe id
   validation everywhere a filesystem path is built from a caller-supplied
   id, configurable upload size limit + zero-byte rejection, absolute-path
   redaction in every persisted error message, a full-body failure-
   isolation wrap added to `report.py` (the one remaining gap vs.
   `processing.py`/`intelligence.py`/`questionnaire.py`'s existing
   pattern), structured per-operation + per-HTTP-request logging
   (`core/observability.py`), a `token_usage: null` convention on every
   `MockAIProvider` metadata dict, a `GET /ready` capability/readiness
   endpoint, a reusable `evidence_integrity` checker, a small pytest
   regression suite (`backend/tests/`), a reproducible engineering-only
   evaluation harness (`scripts/evaluate.py` + `evaluation/`), a repo
   hygiene pass, `docs/DEPLOYMENT.md`, a recruiter-quality `README.md`, and
   a minimal test-only CI workflow. No new product features — see
   `docs/BUILD_STATUS.md` for exact scope. **This was the final planned
   main development phase** — see `docs/BUILD_STATUS.md` for what remains
   for an actual deployment phase (P1+).
7. **P1 — deployment phase, in progress.** P1.1 (baseline verification)
   done. ~~P1.2 — real OpenAI provider adapter~~ — **code done, not
   live-tested**: `OpenAIProvider` implements the full `AIProvider`
   interface behind `AI_PROVIDER=openai`; `MockAIProvider` remains the
   default and is unaffected. No real API key has been used yet — see
   `docs/BUILD_STATUS.md` for exactly what is/isn't verified. Not started:
   a live credential smoke test, database migration, authentication, cloud
   deployment, embeddings/vector DB, RAG, a final evaluation benchmark
   against a real provider, large automated test suite beyond the S7
   critical-path suite, comprehensive security hardening beyond S7's
   pragmatic pass, Kubernetes/Terraform, elaborate monitoring stack.

Do not start a phase early — follow explicit instructions per step.
