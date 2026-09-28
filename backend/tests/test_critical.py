"""Focused regression tests for Resonance's highest-risk behaviors.

Deliberately small — this is not a push for coverage percentage, only the
contracts explicitly called out for S7 hardening: upload validation, path
safety, project isolation, failure isolation, idempotency, evidence
integrity, questionnaire-edit preservation, report/PDF generation, and
overview stage derivation.
"""

from app.core.config import settings
from app.services import evidence_integrity, storage

SAMPLE_TXT = (
    b"This tool has been a great experience overall. The onboarding was easy.\n"
    b"However, there is a recurring problem with the export feature: it fails\n"
    b"intermittently and is quite slow. How can we improve export reliability?\n"
)


def _upload_txt(client, project_id, filename="feedback.txt", content=SAMPLE_TXT):
    resp = client.post(
        f"/projects/{project_id}/upload", files={"file": (filename, content, "text/plain")}
    )
    assert resp.status_code == 200
    return resp.json()


# --- upload validation ------------------------------------------------


def test_upload_rejects_unsupported_type(client, project):
    resp = client.post(
        f"/projects/{project['id']}/upload",
        files={"file": ("malware.exe", b"whatever", "application/octet-stream")},
    )
    assert resp.status_code == 400


def test_upload_rejects_file_above_configured_size_limit(client, project, monkeypatch):
    monkeypatch.setattr(settings, "max_upload_size_mb", 1)
    big_content = b"a" * (2 * 1024 * 1024)
    resp = client.post(
        f"/projects/{project['id']}/upload",
        files={"file": ("big.txt", big_content, "text/plain")},
    )
    assert resp.status_code == 413


def test_upload_rejects_empty_file(client, project):
    resp = client.post(
        f"/projects/{project['id']}/upload", files={"file": ("empty.txt", b"", "text/plain")}
    )
    assert resp.status_code == 400


def test_upload_accepts_file_within_limit(client, project):
    asset = _upload_txt(client, project["id"])
    assert asset["original_filename"] == "feedback.txt"
    assert asset["size_bytes"] == len(SAMPLE_TXT)


# --- safe filename / path handling -------------------------------------


def test_stored_filename_strips_unsafe_characters_from_traversal_attempt(client, project):
    asset = _upload_txt(client, project["id"], filename="../../evil../../name.txt")
    # the directory components are stripped; only a sanitized stem + a
    # random prefix + the real extension may appear in the stored filename
    assert "/" not in asset["stored_filename"]
    assert "\\" not in asset["stored_filename"]
    assert ".." not in asset["stored_filename"]
    assert asset["stored_filename"].endswith(".txt")


def test_stored_path_is_relative_not_absolute(client, project):
    asset = _upload_txt(client, project["id"])
    assert not asset["stored_path"].startswith("/")
    assert ":" not in asset["stored_path"][:3]  # no Windows drive letter (e.g. "C:")


# --- project/asset isolation and id safety ------------------------------


def test_unknown_project_id_returns_404_not_500(client):
    resp = client.get("/projects/does-not-exist")
    assert resp.status_code == 404


def test_malformed_project_id_returns_404_not_500(client):
    resp = client.get("/projects/not a valid id!!")
    assert resp.status_code == 404


def test_project_id_path_traversal_is_rejected_at_storage_layer(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", str(tmp_path / "data"))
    for malicious_id in ("../../../etc", "..", "a/b", "a\\b", "a" * 300):
        try:
            storage.get_project(malicious_id)
            raise AssertionError(f"expected ProjectNotFoundError for id={malicious_id!r}")
        except storage.ProjectNotFoundError:
            pass
    # and no directory should have been created outside the configured data root
    assert not (tmp_path / "etc").exists()


def test_asset_from_one_project_not_visible_via_another_project(client):
    resp_a = client.post("/projects", json={"name": "Project A", "description": ""})
    project_a = resp_a.json()
    resp_b = client.post("/projects", json={"name": "Project B", "description": ""})
    project_b = resp_b.json()

    asset = _upload_txt(client, project_a["id"])

    resp = client.get(f"/projects/{project_b['id']}/assets/{asset['id']}")
    assert resp.status_code == 404


# --- processing failure isolation ---------------------------------------


def test_corrupt_pdf_fails_without_blocking_other_assets(client, project):
    good_asset = _upload_txt(client, project["id"])
    resp = client.post(
        f"/projects/{project['id']}/upload",
        files={"file": ("corrupt.pdf", b"not a real pdf, just bytes", "application/pdf")},
    )
    bad_asset = resp.json()

    good_result = client.post(f"/projects/{project['id']}/assets/{good_asset['id']}/process")
    bad_result = client.post(f"/projects/{project['id']}/assets/{bad_asset['id']}/process")

    assert good_result.status_code == 200
    assert good_result.json()["status"] == "completed"
    assert bad_result.status_code == 200
    assert bad_result.json()["status"] == "failed"
    assert bad_result.json()["error"]  # a useful message, not silently swallowed


def test_retry_overwrites_rather_than_duplicates(client, project):
    resp = client.post(
        f"/projects/{project['id']}/upload",
        files={"file": ("corrupt.pdf", b"not a real pdf, just bytes", "application/pdf")},
    )
    asset = resp.json()

    first = client.post(f"/projects/{project['id']}/assets/{asset['id']}/process").json()
    retried = client.post(f"/projects/{project['id']}/assets/{asset['id']}/retry").json()

    assert first["id"] == retried["id"]

    results = client.get(f"/projects/{project['id']}/processing-results").json()
    assert len(results) == 1


# --- workflow idempotency + questionnaire edit preservation -------------


def test_workflow_is_idempotent_and_preserves_questionnaire_edits(client, project):
    _upload_txt(client, project["id"], filename="feedback1.txt")
    _upload_txt(client, project["id"], filename="feedback2.txt")

    run1 = client.post(f"/projects/{project['id']}/workflow/run", json={}).json()
    assert run1["intelligence_action"] == "generated"
    assert run1["questionnaire_action"] == "generated"
    assert run1["report_action"] == "generated"

    questionnaire_id = run1["questionnaire_id"]
    questionnaire = client.get(
        f"/projects/{project['id']}/questionnaires/{questionnaire_id}"
    ).json()
    edited = []
    for q in questionnaire["questions"]:
        q = dict(q)
        q["text"] = "[EDITED] " + q["text"]
        edited.append(q)
    save_resp = client.put(
        f"/projects/{project['id']}/questionnaires/{questionnaire_id}",
        json={"questions": edited},
    )
    assert save_resp.status_code == 200

    run2 = client.post(f"/projects/{project['id']}/workflow/run", json={}).json()
    assert run2["intelligence_action"] == "reused"
    assert run2["questionnaire_action"] == "reused"
    assert run2["report_action"] == "reused"
    assert run2["intelligence_id"] == run1["intelligence_id"]
    assert run2["questionnaire_id"] == questionnaire_id
    assert run2["report_id"] == run1["report_id"]

    # no uncontrolled duplication
    assert len(client.get(f"/projects/{project['id']}/intelligence").json()) == 1
    assert len(client.get(f"/projects/{project['id']}/questionnaires").json()) == 1
    assert len(client.get(f"/projects/{project['id']}/reports").json()) == 1

    # the manual edit survived the second run
    still_edited = client.get(
        f"/projects/{project['id']}/questionnaires/{questionnaire_id}"
    ).json()
    assert still_edited["questions"][0]["text"].startswith("[EDITED]")


# --- evidence integrity --------------------------------------------------


def test_evidence_integrity_passes_for_real_generated_intelligence(client, project):
    _upload_txt(client, project["id"], filename="feedback1.txt")
    _upload_txt(client, project["id"], filename="feedback2.txt")
    run = client.post(f"/projects/{project['id']}/workflow/run", json={}).json()

    report = evidence_integrity.check_evidence_integrity(project["id"], run["intelligence_id"])
    assert report.total_evidence_items > 0
    assert report.all_valid
    assert report.invalid_evidence_items == 0


def test_evidence_integrity_flags_a_tampered_reference(client, project):
    _upload_txt(client, project["id"], filename="feedback1.txt")
    _upload_txt(client, project["id"], filename="feedback2.txt")
    run = client.post(f"/projects/{project['id']}/workflow/run", json={}).json()

    intelligence = storage.get_project_intelligence(project["id"], run["intelligence_id"])
    tampered = intelligence.model_copy(deep=True)
    tampered.evidence[0].asset_id = "not-a-real-asset-id"
    storage.save_project_intelligence(tampered)

    report = evidence_integrity.check_evidence_integrity(project["id"], run["intelligence_id"])
    assert not report.all_valid
    assert report.invalid_evidence_items == 1
    assert report.issues[0].reason.startswith("asset_id does not reference")


# --- report / PDF generation ---------------------------------------------


def test_report_generation_produces_a_downloadable_pdf(client, project):
    _upload_txt(client, project["id"])
    run = client.post(f"/projects/{project['id']}/workflow/run", json={}).json()

    report = client.get(f"/projects/{project['id']}/reports/{run['report_id']}").json()
    assert report["pdf_path"]

    pdf_resp = client.get(f"/projects/{project['id']}/reports/{run['report_id']}/pdf")
    assert pdf_resp.status_code == 200
    assert pdf_resp.headers["content-type"] == "application/pdf"
    assert pdf_resp.content[:5] == b"%PDF-"


# --- project overview stage behavior --------------------------------------


def test_overview_reports_not_started_for_empty_project(client, project):
    overview = client.get(f"/projects/{project['id']}/overview").json()
    assert overview["overall_pipeline_status"] == "not_started"
    assert overview["current_stage"] == "upload_assets"
    assert overview["blockers"]


def test_overview_reports_completed_after_full_workflow_run(client, project):
    _upload_txt(client, project["id"])
    client.post(f"/projects/{project['id']}/workflow/run", json={})

    overview = client.get(f"/projects/{project['id']}/overview").json()
    assert overview["overall_pipeline_status"] == "completed"
    assert overview["current_stage"] == "done"
    assert overview["pdf_available"] is True


def test_readiness_endpoint_reports_required_checks(client):
    resp = client.get("/ready")
    assert resp.status_code in (200, 503)
    body = resp.json()
    assert "ready" in body
    required_names = {c["name"] for c in body["checks"] if c["required"]}
    assert "data_directory_writable" in required_names
    assert "ai_provider_configured" in required_names
