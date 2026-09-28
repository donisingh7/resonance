# Resonance — Build Status

Last updated: 2026-09-28 (S5 / R4 — questionnaire generation + executive reporting + risk/moderation flags, mock provider)

## Implemented

**Backend (FastAPI, `backend/app/`)**
- `GET /health`
- `POST /projects`, `GET /projects/{project_id}`
- `POST /projects/{project_id}/upload`, `GET .../assets`, `GET .../assets/{asset_id}` (unchanged)
- `POST /projects/{project_id}/assets/{asset_id}/process`, `GET .../processing-results`,
  `GET .../processing-results/{result_id}` (unchanged from S3)
- `POST/GET /projects/{project_id}/intelligence`, `GET .../intelligence/{intelligence_id}` (unchanged from S4)
- **New: `POST /projects/{project_id}/questionnaires`** — generates a
  follow-up `Questionnaire` from a project's intelligence. Optional JSON
  body `{"provider": "mock", "intelligence_id": "..."}`; if `intelligence_id`
  is omitted, the most recently generated `ProjectIntelligence` for the
  project is used. Returns `400` if the project has no intelligence at all
  and none was specified. Idempotent: `uuid5(intelligence_id, provider_name)`
  — regenerating for the same intelligence/provider overwrites the previous
  questionnaire (including any manual edits).
- **New: `GET /projects/{project_id}/questionnaires`** — lists all
  questionnaires for a project, sorted by `created_at`.
- **New: `GET /projects/{project_id}/questionnaires/{questionnaire_id}`**
- **New: `PUT /projects/{project_id}/questionnaires/{questionnaire_id}`** —
  replaces the `questions` list (full array) for manual editing. Preserves
  `id`/`project_id`/`intelligence_id`/`provider`/`status`/`created_at`;
  bumps `updated_at`.
- **New: `POST /projects/{project_id}/reports`** — generates an
  `ExecutiveReport` from a project's intelligence (and, if one exists for
  that intelligence, its questionnaire). Optional JSON body
  `{"intelligence_id": "...", "questionnaire_id": "..."}`; both default to
  "most recent for this project/intelligence" when omitted. Idempotent:
  `uuid5(intelligence_id)` — regenerating overwrites the previous report
  and its PDF file.
- **New: `GET /projects/{project_id}/reports`** — lists all reports for a
  project, sorted by `created_at`.
- **New: `GET /projects/{project_id}/reports/{report_id}`**
- **New: `GET /projects/{project_id}/reports/{report_id}/pdf`** — streams
  the rendered PDF (`404` if the report has none, e.g. rendering failed).

**Questionnaire model (`backend/app/models/questionnaire.py`)**
`Questionnaire`: `id, project_id, intelligence_id, provider, status
(completed|failed), created_at, updated_at, questions, error`.
`Question`: `id, question_type (likert|multiple_choice|free_text|yes_no),
text, rationale, related_theme, required, options`. `related_theme`, when
set, is always literal text copied from the source `ProjectIntelligence`
(a theme, pain point, concern, opportunity, or the sentiment summary) — the
generation logic never invents a new signal, it only reformulates existing
intelligence output into follow-up prompts.

**ExecutiveReport model (`backend/app/models/report.py`)**
`id, project_id, intelligence_id, questionnaire_id, status
(completed|failed), provider, created_at, executive_summary,
source_coverage, overall_sentiment, top_themes, pain_points,
positive_signals, questions_or_concerns, opportunities,
recommended_actions, evidence, questionnaire_summary, risk_flags,
pdf_path, error`. Every factual section (themes, pain points, evidence,
etc.) is copied **verbatim** from the source `ProjectIntelligence` — the
report service never regenerates or reinterprets content, so evidence
traceability (`EvidenceItem`: category, statement, asset_id,
processing_result_id, source_filename, excerpt) is preserved automatically
with no new invented evidence. `provider` is copied from the source
intelligence (e.g. `"mock"`), since generating a report doesn't itself call
an AI provider — it's a structured repackaging step.

**Risk/moderation flags (`RiskFlag`: code, severity, message, details)** —
deterministic, rule-based pipeline/data-quality checks computed from real
counts already on the `ProjectIntelligence`/project state. **Explicitly not
a content-moderation or safety classifier** — no keyword-based judgment of
the content itself is performed. Flags implemented:
| Code | Severity | Trigger |
|---|---|---|
| `intelligence_generation_failed` | critical | source intelligence `status == "failed"` |
| `no_assets` | critical | project has zero uploaded assets |
| `no_source_coverage` | critical | assets exist but zero contributed usable content |
| `low_source_coverage` | warning | fewer than half the project's assets contributed |
| `processing_failures` | warning | one or more processing results failed and were excluded |
| `empty_content_excluded` | info | one or more completed results had no usable text |
| `asset_context_capped` | info | project exceeded the S4 per-run analysis cap |
| `insufficient_supporting_evidence` | warning | content exists but no evidence items were generated |
| `mock_provider_output` | warning | the source intelligence's provider is `"mock"` (always true this phase) |
| `no_questionnaire_generated` | info | no questionnaire exists yet for this intelligence |
| `questionnaire_generation_failed` | warning | a questionnaire exists but its status is `"failed"` |
| `pdf_generation_failed` | warning | PDF rendering raised an exception (isolated, doesn't fail the report) |

**AI provider abstraction (`backend/app/services/ai_providers/`)** — extended for S5:
- `base.py` — `AIProvider` gains `generate_questionnaire(intelligence:
  IntelligenceContext) -> QuestionnaireGenerationResult`. `IntelligenceContext`
  is the subset of an already-generated `ProjectIntelligence`'s fields
  (summary, themes, sentiment, pain points, positive signals, concerns,
  opportunities) — no raw asset text is re-read for questionnaire
  generation, only the already-synthesized S4 output.
- `mock_provider.py` — `MockAIProvider.generate_questionnaire()` is
  deterministic: one `multiple_choice` question per top theme (up to 3),
  one `likert` question per pain point (up to 5), one `free_text` question
  per open question/concern (up to 3), one `yes_no` question per
  opportunity (up to 2), one `yes_no` sentiment-validation question, and
  one always-included closing `free_text` "anything else?" question.
  MockAIProvider's own "[mock] No X detected..." placeholder strings (from
  S4, when a bucket found nothing) are filtered out before question
  generation so the questionnaire doesn't ask about a non-finding.
- `__init__.py` — unchanged factory; no new provider implemented this phase.

**Questionnaire service (`backend/app/services/questionnaire.py`, S5)**
`generate_questionnaire(project_id, intelligence_id=None, provider_name=None)`:
resolves the target intelligence via `intelligence.resolve_intelligence()`
(shared with the report service), calls
`provider.generate_questionnaire()`, and persists the result. A provider
exception is caught and turned into `status="failed"`, mirroring
`processing.py`/`intelligence.py`. `update_questionnaire(project_id,
questionnaire_id, questions)` replaces the question list for manual edits.

**Report service (`backend/app/services/report.py`, S5)**
`generate_report(project_id, intelligence_id=None, questionnaire_id=None)`:
resolves the target intelligence and (optionally) its questionnaire,
builds `source_coverage` from real counts (`storage.list_assets` +
`ProjectIntelligence.processing_metadata`), builds a templated
`[mock report]`-labeled executive summary, computes risk flags, and
attempts PDF rendering — a PDF failure is caught and recorded as a
`pdf_generation_failed` risk flag rather than failing the whole report.

**PDF rendering (`backend/app/services/report_pdf.py`, S5)** — uses
`reportlab` (pure-Python, no system dependency) to render an
`ExecutiveReport` to PDF: title, executive summary, a coverage table, all
list sections as bullet lists, every evidence item with its source
filename/asset id/result id/excerpt, the questionnaire summary, and all
risk flags. Every dynamic string is XML-escaped before being placed in a
`reportlab` `Paragraph` (whose markup is a small XML dialect) so that real
content containing `&`/`<`/`>` can't raise a parse error and crash report
generation. **Dependency check performed before use**: `reportlab` was not
already present in the project's `.venv`; it was installed there only
(`pip install reportlab` inside `.venv`, never touching the machine's
global Python environment) and succeeded on the first attempt, so the PDF
path is fully available this phase — no HTML/Markdown fallback was needed.

**Persistence** — extended: `data/projects/{project_id}/questionnaires/{questionnaire_id}.json`
and `data/projects/{project_id}/reports/{report_id}.json` (+ sibling
`{report_id}.pdf` when rendering succeeds), alongside the existing
`project.json`, `uploads/`, `assets/`, `processing_results/`,
`intelligence/`. All new persistence uses `encoding="utf-8"` explicitly,
consistent with the S4 fix.

**Frontend (Streamlit, `frontend/app.py`)** — two new sections on the
active project page, after the existing "Project intelligence" section:
- **"Follow-up questionnaire"**: "Generate follow-up questionnaire" button;
  each questionnaire is shown in an expander with a "MockAIProvider output"
  caption when applicable, and an editable form per questionnaire (text,
  type, required, comma-separated options per question, with rationale/
  related-theme shown read-only for traceability) plus a "Save
  questionnaire" button that `PUT`s the edited list.
- **"Executive report"**: "Generate executive report" button; each report
  is shown in an expander with a "Download PDF" link-button (hidden if no
  PDF was generated), all risk flags rendered via `st.error`/`st.warning`/
  `st.info` by severity, executive summary, source/asset coverage JSON, all
  list sections, questions/concerns, the linked questionnaire summary, and
  every evidence item with its source/asset/result ids and excerpt.

## Current architecture

```
resonance/
├── backend/app/
│   ├── main.py                    # + questionnaires, reports routers
│   ├── api/
│   │   ├── health.py
│   │   ├── projects.py
│   │   ├── assets.py
│   │   ├── processing_results.py
│   │   ├── intelligence.py
│   │   ├── questionnaires.py      # POST / GET list / GET / PUT (S5)
│   │   └── reports.py             # POST / GET list / GET / GET pdf (S5)
│   ├── core/config.py
│   ├── models/
│   │   ├── project.py
│   │   ├── asset.py
│   │   ├── processing.py
│   │   ├── intelligence.py        # ProjectIntelligence, EvidenceItem
│   │   ├── questionnaire.py       # Questionnaire, Question (S5)
│   │   └── report.py              # ExecutiveReport, RiskFlag (S5)
│   └── services/
│       ├── storage.py             # + questionnaire/report persistence
│       ├── ingestion.py
│       ├── processing.py
│       ├── intelligence.py        # + resolve_intelligence() shared helper
│       ├── questionnaire.py       # follow-up questionnaire service (S5)
│       ├── report.py              # executive report + risk flags (S5)
│       ├── report_pdf.py          # reportlab PDF rendering (S5)
│       ├── video_tools.py
│       └── ai_providers/
│           ├── base.py            # + generate_questionnaire, IntelligenceContext
│           ├── mock_provider.py   # + generate_questionnaire() heuristic
│           └── __init__.py
├── frontend/app.py                # + questionnaire + report sections
├── data/                          # gitignored, runtime (incl. report PDFs)
├── requirements.txt                # + reportlab==5.0.1
├── .env.example
├── CLAUDE.md
└── docs/BUILD_STATUS.md
```

## Known limitations

- **All questionnaire and report content is deterministic mock output**,
  not real AI analysis — themes/questions come from the same S4 keyword
  heuristics, questions are templated per-bucket, and the executive summary
  is a fixed template. Every mock-derived piece of text is labeled
  `[mock]` / `[mock report]` and the UI shows an explicit "MockAIProvider
  output" caption; the `mock_provider_output` risk flag makes this
  unavoidable to notice in the report itself too.
- Risk/moderation flags are pipeline/data-quality checks only — there is
  **no content-moderation or safety classifier** in this phase, by design
  (the task explicitly called for trustworthy-pipeline flags first; adding
  a keyword-based "safety" rule was deliberately skipped rather than
  building something that could be mistaken for real moderation).
  `questionnaire.py`'s `related_theme` values are grounded in real
  `ProjectIntelligence` text, not raw asset content, but that intelligence
  text is itself S4's keyword-heuristic mock output, not human review.
- Editing a questionnaire only replaces the full `questions` array (no
  partial-field patch, no add/remove-question endpoint distinct from
  resending the array) — simplest approach given file-based storage and no
  concurrent-editor concerns at this stage.
- Regenerating a questionnaire or report overwrites the previous one for
  that intelligence/provider, **including manual questionnaire edits** —
  same idempotency strategy as S3/S4, applied consistently, but worth
  knowing before clicking "Generate" again after editing.
- A report's `provider` is inherited from its source intelligence; there is
  no independent "generate this report with a different provider" option,
  since generating a report doesn't call a provider itself.
- No questionnaire/report versioning or diffing — each is a single current
  snapshot per (intelligence, provider).
- No authentication, no database, no queues, no containerization/deployment.
- No automated test suite — verified via one manual smoke pass (see below).

## Smoke-tested this phase

Backend started locally (`.venv`); full flow exercised via scripted HTTP
calls against a running instance:
- Re-verified unaffected: health check, project create/get, upload, asset
  list/get, asset processing (TXT/PDF), processing-result list/get,
  project intelligence generation — all still return 200 with expected
  shapes.
- Questionnaire generation on a project **with no intelligence yet**
  returns `400` with a clear message rather than a crash or a nonsensical
  empty questionnaire.
- Questionnaire generation on a project with 2 processed TXT assets:
  `status="completed"`, non-empty `questions`, every `related_theme`
  verified (programmatically, in the smoke script) to be a literal
  substring of the source `ProjectIntelligence`'s own themes/pain
  points/concerns/opportunities/sentiment — no invented signal.
- Questionnaire **idempotency**: regenerating returns the same `id`; list
  endpoint still shows exactly 1 record.
- Questionnaire **edit/save**: `PUT` with modified question text persists
  the edit, preserves `created_at`, and bumps `updated_at`.
- Executive report generation: evidence count matches the source
  intelligence's evidence count exactly (verbatim carry-through); links the
  generated questionnaire via `questionnaire_id`; includes the
  `mock_provider_output` risk flag.
- Report **idempotency**: regenerating returns the same `id`; list endpoint
  still shows exactly 1 record.
- **Mixed project** (one completed + one failed processing result):
  report's risk flags correctly include `processing_failures` and (since no
  questionnaire was generated for it) `no_questionnaire_generated`.
- **Zero-asset project**: report generation succeeds (not an error) and
  flags `no_assets`.
- **Asset uploaded but never processed**: report generation succeeds and
  flags `no_source_coverage` (distinct from `no_assets` — asset exists,
  just never contributed content).
- **PDF download**: verified `Content-Type: application/pdf`, a valid
  `%PDF-` header, non-trivial size, and — via a separate manual render —
  visually inspected the actual PDF pages to confirm all sections,
  evidence, and risk flags render correctly and legibly.
- 404s verified for an unknown questionnaire, an unknown report, and a
  report-PDF request against an unknown project.
- Streamlit booted successfully against the smoke-test backend and served
  its page with no server-side exceptions in the log.
- Not re-tested this phase: audio/image/video asset processing (unchanged
  S3 code path) — same pre-existing local `hachoir` mirror limitation noted
  in the S4 build status, unrelated to S5 changes.

## Next phase (not started)

Final recruiter-grade UI redesign, database migration, authentication,
cloud deployment, embeddings/vector DB, RAG/semantic search, real external
provider credentials, final evaluation benchmark, large automated test
suite, async queues/background workers.
