# Resonance evaluation harness

This is an **engineering / pipeline evaluation**, not an AI-quality
benchmark. It exercises the real end-to-end Resonance workflow (upload →
ingest → process → intelligence → questionnaire → report → PDF →
orchestration) against a temporary, disposable project and measures
**factual, system-level outcomes** — whether things ran, succeeded, stayed
consistent, and produced traceable evidence.

It does **not** attempt to measure whether `MockAIProvider`'s themes,
sentiment, or generated questions are semantically good. They can't be —
`MockAIProvider` is a deterministic keyword/word-frequency heuristic, not a
real model. See the root `README.md` and `docs/BUILD_STATUS.md` for the
full list of what remains mock vs. real.

## What's here

```
evaluation/
├── fixtures/                    # synthetic, safe text fixtures (this run's inputs)
│   ├── feedback_positive.txt    # generic, upbeat synthetic product feedback
│   └── feedback_mixed.txt       # generic feedback with both praise and complaints
└── README.md                    # this file
```

Image and PDF inputs are **generated in-memory at run time** (via Pillow and
`reportlab`, both already project dependencies) rather than committed as
binary fixtures — see `scripts/evaluate.py`. All fixtures were written
specifically for this project: no Bosch, client, or other third-party data.

## Running it

From the repo root, using the project's `.venv`:

```bash
.venv\Scripts\python.exe scripts\evaluate.py
```

The harness:
1. Creates a temporary, isolated Resonance project (own `data_dir`, cleaned
   up automatically — it never touches your real `data/` directory).
2. Uploads the TXT fixtures plus a generated PNG and a deliberately corrupt
   "PDF" (to exercise the failure/isolation path safely).
3. Runs the full pipeline via the S6 workflow orchestration endpoint.
4. Runs it a second time to check idempotency (no duplicate intelligence/
   questionnaire/report records).
5. Edits the generated questionnaire, then re-runs the workflow once more
   to confirm the edit survives (S6's "never silently overwrite an edited
   questionnaire" guarantee).
6. Runs the evidence integrity check (`app.services.evidence_integrity`)
   against the generated intelligence.
7. Downloads the generated PDF and checks its header/size.

## Output

Two things are printed:
1. A concise human-readable summary (pass/fail per check).
2. A machine-readable JSON result, also written under the gitignored
   `runtime/evaluation-results/` directory (created on demand — never
   committed).

## Reading the results

Every metric in the JSON output falls into exactly one of two categories,
and the harness's own printed summary keeps them visually separate:

**A. Measured local engineering metrics** (what this harness actually checks):
files attempted/ingested, processing success/failure counts, workflow
completion state, evidence-reference validity, idempotency, questionnaire-
edit preservation, report/PDF generation, and stage/total latency.

**B. Not yet measured** (would require a real AI provider, out of scope
here): semantic accuracy of themes/sentiment/summaries, transcription
quality, vision quality, real LLM output quality, production throughput,
business ROI.

Never read a passing engineering-metric run as evidence of AI quality —
they are independent axes.
