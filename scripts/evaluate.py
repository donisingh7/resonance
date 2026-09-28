#!/usr/bin/env python
"""Resonance evaluation harness — an ENGINEERING/PIPELINE evaluation, not
an AI-quality benchmark. See evaluation/README.md for exactly what this
does and does not measure.

Runs entirely in-process (FastAPI TestClient, no server/port needed)
against a temporary, isolated data directory that is discarded afterward —
it never touches your real `data/` directory. No external credentials.

Usage (from the repo root):
    .venv\\Scripts\\python.exe scripts\\evaluate.py
"""

import io
import json
import shutil
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import settings  # noqa: E402

_tmp_root = tempfile.mkdtemp(prefix="resonance-eval-")
settings.data_dir = str(Path(_tmp_root) / "data")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.services import evidence_integrity  # noqa: E402

client = TestClient(app)

FIXTURES_DIR = REPO_ROOT / "evaluation" / "fixtures"
RESULTS_DIR = REPO_ROOT / "runtime" / "evaluation-results"


def _generate_png_bytes() -> bytes:
    from PIL import Image

    img = Image.new("RGB", (48, 48), color=(120, 160, 200))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def run_evaluation() -> dict:
    metrics: dict = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "category_a_measured_engineering_metrics": {},
        "category_b_not_yet_measured_ai_quality": {
            "semantic_accuracy": "not measured — MockAIProvider is a deterministic "
            "keyword/word-frequency heuristic, not a real model",
            "transcription_quality": "not measured — no real speech-to-text integrated",
            "vision_quality": "not measured — no real vision model integrated",
            "real_llm_quality": "not measured — no real LLM integrated",
            "production_throughput": "not measured — single local process, not load-tested",
            "business_roi": "not measured — no production usage exists",
        },
        "checks": {},
        "pass": True,
    }

    def record(name: str, ok: bool, detail: str = "") -> None:
        metrics["checks"][name] = {"ok": ok, "detail": detail}
        if not ok:
            metrics["pass"] = False

    metrics_a = metrics["category_a_measured_engineering_metrics"]

    # 1. project create
    resp = client.post(
        "/projects", json={"name": "Evaluation Run", "description": "synthetic evaluation project"}
    )
    record("project_create", resp.status_code == 200, f"status={resp.status_code}")
    project_id = resp.json()["id"]

    # 2. readiness endpoint
    resp = client.get("/ready")
    record("readiness_endpoint", resp.status_code in (200, 503), f"ready={resp.json().get('ready')}")

    # 3. upload fixtures: 2 real TXT, 1 generated PNG, 1 deliberately corrupt "PDF"
    files_attempted = 0
    files_ingested = 0

    for txt_path in sorted(FIXTURES_DIR.glob("*.txt")):
        files_attempted += 1
        resp = client.post(
            f"/projects/{project_id}/upload",
            files={"file": (txt_path.name, txt_path.read_bytes(), "text/plain")},
        )
        if resp.status_code == 200:
            files_ingested += 1

    files_attempted += 1
    resp = client.post(
        f"/projects/{project_id}/upload",
        files={"file": ("synthetic.png", _generate_png_bytes(), "image/png")},
    )
    if resp.status_code == 200:
        files_ingested += 1

    files_attempted += 1
    resp = client.post(
        f"/projects/{project_id}/upload",
        files={"file": ("corrupt.pdf", b"not a real pdf, just bytes", "application/pdf")},
    )
    if resp.status_code == 200:
        files_ingested += 1

    record("files_ingested", files_ingested == files_attempted, f"{files_ingested}/{files_attempted}")
    metrics_a["files_attempted"] = files_attempted
    metrics_a["files_ingested_successfully"] = files_ingested

    # 4. run workflow (first pass) — processes assets, generates intelligence/
    # questionnaire/report/PDF in one call
    started = time.monotonic()
    resp = client.post(f"/projects/{project_id}/workflow/run", json={})
    workflow_latency_ms = round((time.monotonic() - started) * 1000, 1)
    record("workflow_run_1", resp.status_code == 200, f"status={resp.status_code}")
    run1 = resp.json()

    processing_success = len(run1["asset_processing_successes"])
    processing_failure = len(run1["asset_processing_failures"])
    metrics_a["processing_success_count"] = processing_success
    metrics_a["processing_failure_count"] = processing_failure
    metrics_a["workflow_completion_state"] = run1["overview"]["overall_pipeline_status"]
    metrics_a["total_workflow_latency_ms"] = workflow_latency_ms
    metrics_a["stages_completed"] = run1["stages_completed"]
    metrics_a["stages_skipped"] = run1["stages_skipped"]

    record(
        "processing_failure_isolated",
        processing_failure >= 1 and processing_success >= 2,
        f"successes={processing_success} failures={processing_failure} "
        f"(expect the corrupt PDF to fail without blocking the others)",
    )
    record("intelligence_generated", run1["intelligence_action"] == "generated")
    record("questionnaire_generated", run1["questionnaire_action"] == "generated")
    record("report_generated", run1["report_action"] == "generated")

    intelligence_id = run1["intelligence_id"]
    questionnaire_id = run1["questionnaire_id"]
    report_id = run1["report_id"]

    # 5. evidence integrity — every evidence item must reference a real
    # asset/processing-result/filename; never repaired, only reported
    integrity_report = evidence_integrity.check_evidence_integrity(project_id, intelligence_id)
    record(
        "evidence_integrity",
        integrity_report.all_valid,
        f"valid={integrity_report.valid_evidence_items} invalid={integrity_report.invalid_evidence_items}",
    )
    metrics_a["evidence_total"] = integrity_report.total_evidence_items
    metrics_a["evidence_valid"] = integrity_report.valid_evidence_items
    metrics_a["evidence_invalid"] = integrity_report.invalid_evidence_items

    # 6. edit the questionnaire
    resp = client.get(f"/projects/{project_id}/questionnaires/{questionnaire_id}")
    questionnaire = resp.json()
    edited_questions = []
    for q in questionnaire["questions"]:
        edited = dict(q)
        edited["text"] = "[EVAL EDIT] " + q["text"]
        edited_questions.append(edited)
    resp = client.put(
        f"/projects/{project_id}/questionnaires/{questionnaire_id}",
        json={"questions": edited_questions},
    )
    record("questionnaire_edit_saved", resp.status_code == 200)

    # 7. run the workflow again — checks idempotency AND that the edit survives
    resp = client.post(f"/projects/{project_id}/workflow/run", json={})
    run2 = resp.json()
    idempotent = (
        run2["intelligence_id"] == intelligence_id
        and run2["questionnaire_id"] == questionnaire_id
        and run2["report_id"] == report_id
        and run2["intelligence_action"] == "reused"
        and run2["questionnaire_action"] == "reused"
    )
    record(
        "idempotency_check",
        idempotent,
        f"run2 actions: intelligence={run2['intelligence_action']} "
        f"questionnaire={run2['questionnaire_action']} report={run2['report_action']}",
    )

    resp = client.get(f"/projects/{project_id}/questionnaires/{questionnaire_id}")
    edit_preserved = resp.json()["questions"][0]["text"].startswith("[EVAL EDIT]")
    record("questionnaire_edit_preservation", edit_preserved)

    # 8. report + PDF
    resp = client.get(f"/projects/{project_id}/reports/{report_id}")
    record("report_fetchable", resp.status_code == 200)
    report = resp.json()

    pdf_generated = bool(report.get("pdf_path"))
    record("pdf_generated", pdf_generated)
    if pdf_generated:
        resp = client.get(f"/projects/{project_id}/reports/{report_id}/pdf")
        pdf_ok = resp.status_code == 200 and resp.content[:5] == b"%PDF-"
        record("pdf_downloadable", pdf_ok, f"size={len(resp.content)} bytes")
        metrics_a["pdf_size_bytes"] = len(resp.content)

    metrics["finished_at"] = datetime.now(timezone.utc).isoformat()
    return metrics


def print_summary(metrics: dict) -> None:
    print("=" * 72)
    print("Resonance evaluation harness — ENGINEERING/PIPELINE run")
    print("(not an AI-quality benchmark — see evaluation/README.md)")
    print("=" * 72)
    for name, check in metrics["checks"].items():
        status = "PASS" if check["ok"] else "FAIL"
        detail = f" — {check['detail']}" if check.get("detail") else ""
        print(f"[{status}] {name}{detail}")
    print("-" * 72)
    print("Category A — measured local engineering metrics:")
    for key, value in metrics["category_a_measured_engineering_metrics"].items():
        print(f"  {key}: {value}")
    print("-" * 72)
    print("Category B — NOT yet measured (would require a real AI provider):")
    for key, value in metrics["category_b_not_yet_measured_ai_quality"].items():
        print(f"  {key}: {value}")
    print("=" * 72)
    print(f"Overall: {'PASS' if metrics['pass'] else 'FAIL'}")


if __name__ == "__main__":
    try:
        result = run_evaluation()
    finally:
        shutil.rmtree(_tmp_root, ignore_errors=True)

    print_summary(result)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = RESULTS_DIR / f"eval_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    out_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"\nJSON result written to: {out_path.relative_to(REPO_ROOT)}")

    sys.exit(0 if result["pass"] else 1)
