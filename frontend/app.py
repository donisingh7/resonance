import os

import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

st.set_page_config(page_title="Resonance", layout="wide")


# ---------------------------------------------------------------------------
# Backend call helpers — every call goes through here so failures render as
# a user-facing message instead of a raw stack trace anywhere in the app.
# ---------------------------------------------------------------------------


def api_get(path: str, timeout: int = 10):
    try:
        return requests.get(f"{BACKEND_URL}{path}", timeout=timeout)
    except requests.exceptions.RequestException:
        return None


def api_post(path: str, json=None, files=None, timeout: int = 30):
    try:
        return requests.post(f"{BACKEND_URL}{path}", json=json, files=files, timeout=timeout)
    except requests.exceptions.RequestException:
        return None


def api_put(path: str, json=None, timeout: int = 15):
    try:
        return requests.put(f"{BACKEND_URL}{path}", json=json, timeout=timeout)
    except requests.exceptions.RequestException:
        return None


def show_backend_error(resp, action: str):
    """Renders one user-facing error line for a failed/unreachable call.
    Never surfaces a raw stack trace."""
    if resp is None:
        st.error(f"Could not reach the backend while trying to {action}. Is it running?")
        return
    try:
        detail = resp.json().get("detail", resp.text)
    except Exception:
        detail = resp.text
    st.error(f"Failed to {action} ({resp.status_code}): {detail}")


# ---------------------------------------------------------------------------
# Project selection
# ---------------------------------------------------------------------------


def render_project_picker():
    st.subheader("Project")
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Create a new project**")
        with st.form("create_project_form"):
            project_name = st.text_input("Name")
            project_description = st.text_area("Description", height=80)
            submitted = st.form_submit_button("Create project")
            if submitted:
                if not project_name.strip():
                    st.warning("Name is required.")
                else:
                    resp = api_post(
                        "/projects", json={"name": project_name, "description": project_description}
                    )
                    if resp is not None and resp.status_code == 200:
                        project = resp.json()
                        st.session_state["active_project_id"] = project["id"]
                        st.success(f"Project created: {project['name']}")
                        st.rerun()
                    else:
                        show_backend_error(resp, "create the project")

    with col2:
        st.markdown("**Open an existing project**")
        resp = api_get("/projects")
        projects = resp.json() if resp is not None and resp.status_code == 200 else []

        if projects:
            projects_sorted = sorted(projects, key=lambda p: p["created_at"], reverse=True)
            options = {f"{p['name']} ({p['id'][:8]})": p["id"] for p in projects_sorted}
            labels = list(options.keys())
            current_id = st.session_state.get("active_project_id")
            default_index = next(
                (i for i, pid in enumerate(options.values()) if pid == current_id), 0
            )
            selected_label = st.selectbox("Select a project", labels, index=default_index)
            if st.button("Open selected project"):
                st.session_state["active_project_id"] = options[selected_label]
                st.rerun()
        else:
            st.caption("No projects yet — create one to get started.")

        with st.expander("Open by project ID"):
            manual_id = st.text_input("Project ID", key="manual_project_id")
            if st.button("Load by ID") and manual_id.strip():
                st.session_state["active_project_id"] = manual_id.strip()
                st.rerun()

    active_project_id = st.session_state.get("active_project_id")
    if not active_project_id:
        return None

    resp = api_get(f"/projects/{active_project_id}")
    if resp is None or resp.status_code != 200:
        st.error(f"Could not load project '{active_project_id}'.")
        return None

    project = resp.json()
    st.success(f"Active project: **{project['name']}** (`{project['id']}`)")
    return project


# ---------------------------------------------------------------------------
# Overview tab
# ---------------------------------------------------------------------------

_STATUS_ICONS = {
    "not_started": "⚪",
    "ready": "🔵",
    "in_progress": "🟡",
    "partial": "🟠",
    "completed": "🟢",
    "blocked": "🔴",
    "failed": "🔴",
}


def render_overview_tab(project: dict, ov: dict | None):
    project_id = project["id"]

    if st.button("🚀 Run Remaining Pipeline", type="primary"):
        with st.spinner("Running the pipeline — processing assets, generating intelligence, "
                         "questionnaire, and report as needed..."):
            resp = api_post(f"/projects/{project_id}/workflow/run", json={}, timeout=180)
        if resp is not None and resp.status_code == 200:
            result = resp.json()
            st.success("Pipeline run complete.")
            st.write(
                f"Completed: {', '.join(result['stages_completed']) or 'none'}  \n"
                f"Skipped (already up to date): {', '.join(result['stages_skipped']) or 'none'}"
            )
            if result["asset_processing_successes"]:
                st.write(f"Assets processed successfully: {len(result['asset_processing_successes'])}")
            if result["asset_processing_failures"]:
                st.warning(
                    f"{len(result['asset_processing_failures'])} asset(s) failed processing "
                    f"during this run — see the Assets tab to retry."
                )
            for w in result["warnings"]:
                st.warning(w)
            st.rerun()
        else:
            show_backend_error(resp, "run the pipeline")

    st.divider()

    if ov is None:
        st.error("Could not load the project overview.")
        return

    icon = _STATUS_ICONS.get(ov["overall_pipeline_status"], "")
    st.markdown(f"### {icon} `{ov['overall_pipeline_status']}` — {ov['current_stage'].replace('_', ' ').title()}")
    st.markdown(f"**Next recommended action:** {ov['next_recommended_action']}")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total assets", ov["total_assets"])
    col2.metric("Processed", ov["processed_assets"])
    col3.metric("Pending", ov["pending_processing_assets"])
    col4.metric("Failed", ov["failed_processing_assets"])

    if ov["assets_by_modality"]:
        st.caption("By modality: " + ", ".join(f"{k}: {v}" for k, v in ov["assets_by_modality"].items()))

    col5, col6, col7 = st.columns(3)
    col5.write(
        "**Intelligence:** "
        + (f"✅ {ov['intelligence_status']}" if ov["latest_intelligence_id"] else "⬜ not generated")
    )
    col6.write("**Questionnaire:** " + ("✅ available" if ov["questionnaire_available"] else "⬜ not generated"))
    if ov["report_available"]:
        col7.write("**Report:** ✅ available" + (" (PDF ready)" if ov["pdf_available"] else " (PDF unavailable)"))
    else:
        col7.write("**Report:** ⬜ not generated")

    if ov["blockers"]:
        st.markdown("**Blockers**")
        for b in ov["blockers"]:
            st.error(b)
    if ov["warnings"]:
        st.markdown("**Warnings**")
        for w in ov["warnings"]:
            st.warning(w)


# ---------------------------------------------------------------------------
# Assets tab
# ---------------------------------------------------------------------------


def render_assets_tab(project: dict):
    project_id = project["id"]

    st.markdown("**Upload files**")
    uploaded_files = st.file_uploader(
        "Supported: mp3, wav, mp4, jpg, jpeg, png, pdf, txt",
        accept_multiple_files=True,
        key="uploader",
    )
    if uploaded_files and st.button("Upload selected files"):
        success_count = 0
        for f in uploaded_files:
            resp = api_post(
                f"/projects/{project_id}/upload", files={"file": (f.name, f.getvalue())}, timeout=30
            )
            if resp is not None and resp.status_code == 200:
                success_count += 1
            else:
                show_backend_error(resp, f"upload {f.name}")
        if success_count:
            st.success(f"Uploaded {success_count} file(s).")
            st.rerun()

    st.divider()
    st.markdown("**Assets**")

    assets_resp = api_get(f"/projects/{project_id}/assets")
    if assets_resp is None or assets_resp.status_code != 200:
        show_backend_error(assets_resp, "load assets")
        return
    assets = assets_resp.json()

    results_resp = api_get(f"/projects/{project_id}/processing-results")
    results_by_asset: dict[str, dict] = {}
    if results_resp is not None and results_resp.status_code == 200:
        for r in results_resp.json():  # ascending by created_at -> last write is the latest
            results_by_asset[r["asset_id"]] = r

    if not assets:
        st.info("No assets uploaded yet for this project. Upload files above to get started.")
        return

    completed = sum(1 for r in results_by_asset.values() if r["status"] == "completed")
    failed = sum(1 for r in results_by_asset.values() if r["status"] == "failed")
    pending = len(assets) - len(results_by_asset)
    st.caption(f"{len(assets)} asset(s) · {completed} completed · {pending} pending · {failed} failed")

    for asset in assets:
        result = results_by_asset.get(asset["id"])
        if result is None:
            status_label = "⏳ pending"
        elif result["status"] == "completed":
            status_label = "✅ completed"
        else:
            status_label = "❌ failed"

        with st.expander(f"{asset['original_filename']} — {asset['modality']} — {status_label}"):
            st.caption(
                f"mime: {asset['mime_type']} · size: {asset['size_bytes']} bytes · "
                f"ingestion: {asset['ingestion_status']}"
            )
            st.markdown("**Technical metadata**")
            st.json(asset["technical_metadata"])

            if result is None:
                if st.button("Process asset", key=f"process_{asset['id']}"):
                    resp = api_post(f"/projects/{project_id}/assets/{asset['id']}/process", timeout=120)
                    if resp is not None and resp.status_code == 200:
                        st.success("Processing complete.")
                        st.rerun()
                    else:
                        show_backend_error(resp, "process this asset")
            elif result["status"] == "failed":
                if st.button("Retry processing", key=f"retry_{asset['id']}"):
                    resp = api_post(f"/projects/{project_id}/assets/{asset['id']}/retry", timeout=120)
                    if resp is not None and resp.status_code == 200:
                        st.success("Retry complete.")
                        st.rerun()
                    else:
                        show_backend_error(resp, "retry this asset")
            else:
                if st.button("Reprocess", key=f"reprocess_{asset['id']}"):
                    resp = api_post(f"/projects/{project_id}/assets/{asset['id']}/process", timeout=120)
                    if resp is not None and resp.status_code == 200:
                        st.success("Reprocessing complete.")
                        st.rerun()
                    else:
                        show_backend_error(resp, "reprocess this asset")

            if result:
                st.markdown(f"**Provider:** {result['provider']}")
                if result["status"] == "failed":
                    st.error(f"Processing error: {result['error']}")
                else:
                    if result["transcript"]:
                        st.markdown("**Transcript**")
                        st.write(result["transcript"])
                    if result["extracted_text"]:
                        st.markdown("**Extracted text**")
                        st.write(result["extracted_text"])
                    if result["visual_description"]:
                        st.markdown("**Visual description**")
                        st.write(result["visual_description"])
                    st.markdown("**Modality metadata**")
                    st.json(result["modality_metadata"])


# ---------------------------------------------------------------------------
# Intelligence tab
# ---------------------------------------------------------------------------


def render_intelligence_tab(project: dict):
    project_id = project["id"]
    st.caption(
        "Project Intelligence is only generated on request — opening this tab never "
        "triggers generation. Use 'Run Remaining Pipeline' on Overview, or generate it "
        "explicitly below."
    )

    if st.button("Generate / regenerate project intelligence"):
        resp = api_post(f"/projects/{project_id}/intelligence", json={}, timeout=60)
        if resp is not None and resp.status_code == 200:
            st.success("Project intelligence generated.")
            st.rerun()
        else:
            show_backend_error(resp, "generate project intelligence")

    resp = api_get(f"/projects/{project_id}/intelligence")
    if resp is None or resp.status_code != 200:
        show_backend_error(resp, "load project intelligence")
        return

    records = resp.json()
    if not records:
        st.info("No project intelligence generated yet for this project.")
        return

    records = sorted(records, key=lambda r: r["created_at"], reverse=True)
    latest = records[0]

    if latest["status"] == "failed":
        st.error(f"Latest intelligence generation failed: {latest['error']}")
        return

    if latest["provider"] == "mock":
        st.info("MockAIProvider output: deterministic placeholder synthesis, not real AI analysis.")

    st.markdown("### Summary")
    st.write(latest["summary"])

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Top themes**")
        for item in latest["top_themes"]:
            st.write(f"- {item}")
        st.markdown("**Pain points**")
        for item in latest["pain_points"]:
            st.write(f"- {item}")
        st.markdown("**Opportunities**")
        for item in latest["opportunities"]:
            st.write(f"- {item}")
    with col2:
        st.markdown("**Sentiment**")
        st.write(latest["sentiment_summary"])
        st.markdown("**Positive signals**")
        for item in latest["positive_signals"]:
            st.write(f"- {item}")
        st.markdown("**Recommended actions**")
        for item in latest["recommended_actions"]:
            st.write(f"- {item}")

    st.markdown("**Questions / concerns**")
    for item in latest["questions_or_concerns"]:
        st.write(f"- {item}")

    st.caption(
        f"Based on {len(latest['source_result_ids'])} processed asset(s) · "
        f"{len(latest['evidence'])} evidence item(s) — see the Evidence tab."
    )

    if len(records) > 1:
        with st.expander(f"{len(records) - 1} earlier intelligence run(s)"):
            for record in records[1:]:
                st.write(f"- {record['created_at']} — {record['status']} — `{record['id']}`")


# ---------------------------------------------------------------------------
# Questionnaire tab
# ---------------------------------------------------------------------------

_QUESTION_TYPE_OPTIONS = ["likert", "multiple_choice", "free_text", "yes_no"]


def render_questionnaire_tab(project: dict):
    project_id = project["id"]

    if st.button("Generate follow-up questionnaire"):
        resp = api_post(f"/projects/{project_id}/questionnaires", json={}, timeout=30)
        if resp is not None and resp.status_code == 200:
            st.success("Questionnaire generated.")
            st.rerun()
        elif resp is not None and resp.status_code == 400:
            st.warning(resp.json().get("detail", "Generation failed."))
        else:
            show_backend_error(resp, "generate the questionnaire")

    resp = api_get(f"/projects/{project_id}/questionnaires")
    if resp is None or resp.status_code != 200:
        show_backend_error(resp, "load questionnaires")
        return

    questionnaires = resp.json()
    if not questionnaires:
        st.info("No questionnaire generated yet. Generate project intelligence first, then a questionnaire.")
        return

    questionnaires = sorted(questionnaires, key=lambda q: q["created_at"], reverse=True)
    for q in questionnaires:
        label = f"{q['provider']} — {q['status']} — {len(q['questions'])} question(s) — {q['created_at']}"
        with st.expander(label, expanded=(q is questionnaires[0])):
            if q["status"] == "failed":
                st.error(f"Questionnaire generation error: {q['error']}")
                continue

            if q["provider"] == "mock":
                st.caption(
                    "MockAIProvider output: deterministic follow-up questions derived from "
                    "mock project intelligence, not real AI-generated questions."
                )

            with st.form(f"edit_questionnaire_{q['id']}"):
                edited_questions = []
                for question in q["questions"]:
                    st.markdown(f"**Question `{question['id'][:8]}`** — *{question['question_type']}*")
                    text = st.text_area("Text", value=question["text"], key=f"text_{question['id']}")
                    qtype = st.selectbox(
                        "Type",
                        _QUESTION_TYPE_OPTIONS,
                        index=_QUESTION_TYPE_OPTIONS.index(question["question_type"]),
                        key=f"type_{question['id']}",
                    )
                    required = st.checkbox("Required", value=question["required"], key=f"required_{question['id']}")
                    options_text = st.text_input(
                        "Options (comma-separated, blank for none)",
                        value=", ".join(question["options"] or []),
                        key=f"options_{question['id']}",
                    )
                    if question.get("related_theme"):
                        st.caption(f"Related theme: {question['related_theme']}")
                    st.caption(f"Rationale: {question['rationale']}")
                    st.markdown("---")

                    options_list = (
                        [o.strip() for o in options_text.split(",") if o.strip()]
                        if options_text.strip()
                        else None
                    )
                    edited_questions.append(
                        {
                            "id": question["id"],
                            "question_type": qtype,
                            "text": text,
                            "rationale": question["rationale"],
                            "related_theme": question.get("related_theme"),
                            "required": required,
                            "options": options_list,
                        }
                    )

                if st.form_submit_button("Save questionnaire"):
                    save_resp = api_put(
                        f"/projects/{project_id}/questionnaires/{q['id']}",
                        json={"questions": edited_questions},
                    )
                    if save_resp is not None and save_resp.status_code == 200:
                        st.success("Questionnaire saved.")
                        st.rerun()
                    else:
                        show_backend_error(save_resp, "save the questionnaire")


# ---------------------------------------------------------------------------
# Executive report tab
# ---------------------------------------------------------------------------

_SEVERITY_DISPLAY = {"critical": "error", "warning": "warning", "info": "info"}


def render_report_tab(project: dict):
    project_id = project["id"]

    if st.button("Generate executive report"):
        resp = api_post(f"/projects/{project_id}/reports", json={}, timeout=60)
        if resp is not None and resp.status_code == 200:
            st.success("Executive report generated.")
            st.rerun()
        elif resp is not None and resp.status_code == 400:
            st.warning(resp.json().get("detail", "Generation failed."))
        else:
            show_backend_error(resp, "generate the report")

    resp = api_get(f"/projects/{project_id}/reports")
    if resp is None or resp.status_code != 200:
        show_backend_error(resp, "load reports")
        return

    reports = resp.json()
    if not reports:
        st.info("No executive report generated yet. Generate project intelligence first, then a report.")
        return

    reports = sorted(reports, key=lambda r: r["created_at"], reverse=True)
    for rep in reports:
        label = f"{rep['provider']} — {rep['status']} — {rep['created_at']}"
        with st.expander(label, expanded=(rep is reports[0])):
            if rep["provider"] == "mock":
                st.caption(
                    "MockAIProvider output: this entire report is built from deterministic "
                    "mock project intelligence, not real AI analysis."
                )

            if rep.get("pdf_path"):
                st.link_button(
                    "Download PDF",
                    url=f"{BACKEND_URL}/projects/{project_id}/reports/{rep['id']}/pdf",
                )
            else:
                st.caption("PDF not available for this report.")

            st.markdown("**Risk / data-quality flags**")
            if not rep["risk_flags"]:
                st.write("No flags raised.")
            for flag in rep["risk_flags"]:
                display_fn = getattr(st, _SEVERITY_DISPLAY.get(flag["severity"], "info"))
                display_fn(f"[{flag['code']}] {flag['message']}")

            st.markdown("**Executive summary**")
            st.write(rep["executive_summary"])

            st.markdown("**Source / asset coverage**")
            st.json(rep["source_coverage"])

            col1, col2 = st.columns(2)
            with col1:
                st.markdown("**Top themes**")
                for item in rep["top_themes"]:
                    st.write(f"- {item}")
                st.markdown("**Pain points**")
                for item in rep["pain_points"]:
                    st.write(f"- {item}")
                st.markdown("**Opportunities**")
                for item in rep["opportunities"]:
                    st.write(f"- {item}")
            with col2:
                st.markdown("**Overall sentiment**")
                st.write(rep["overall_sentiment"])
                st.markdown("**Positive signals**")
                for item in rep["positive_signals"]:
                    st.write(f"- {item}")
                st.markdown("**Recommended actions**")
                for item in rep["recommended_actions"]:
                    st.write(f"- {item}")

            st.markdown("**Questions / concerns**")
            for item in rep["questions_or_concerns"]:
                st.write(f"- {item}")

            st.markdown("**Follow-up questionnaire**")
            if rep.get("questionnaire_summary"):
                qs = rep["questionnaire_summary"]
                st.write(
                    f"Questionnaire `{qs['questionnaire_id']}` — {qs['question_count']} "
                    f"question(s), status: {qs['status']}."
                )
            else:
                st.write("No questionnaire was generated for this analysis.")

            st.caption(
                f"{len(rep['evidence'])} evidence item(s) supporting this report — "
                f"see the Evidence tab."
            )


# ---------------------------------------------------------------------------
# Evidence explorer tab
# ---------------------------------------------------------------------------


def render_evidence_tab(project: dict):
    project_id = project["id"]

    resp = api_get(f"/projects/{project_id}/intelligence")
    if resp is None or resp.status_code != 200:
        show_backend_error(resp, "load evidence")
        return

    records = resp.json()
    if not records:
        st.info("No project intelligence generated yet — evidence will appear here once it is.")
        return

    latest = sorted(records, key=lambda r: r["created_at"], reverse=True)[0]
    evidence = latest["evidence"]

    if not evidence:
        st.info("The latest project intelligence has no evidence items.")
        return

    st.caption(f"Evidence from the latest intelligence run (`{latest['id']}`), generated {latest['created_at']}.")

    categories = sorted({e["category"] for e in evidence})
    filenames = sorted({e["source_filename"] for e in evidence})
    asset_ids = sorted({e["asset_id"] for e in evidence})

    col1, col2, col3 = st.columns(3)
    with col1:
        selected_categories = st.multiselect("Category", categories, default=categories)
    with col2:
        selected_filenames = st.multiselect("Source filename", filenames, default=filenames)
    with col3:
        selected_assets = st.multiselect("Asset ID", asset_ids, default=asset_ids, format_func=lambda a: a[:8])

    filtered = [
        e
        for e in evidence
        if e["category"] in selected_categories
        and e["source_filename"] in selected_filenames
        and e["asset_id"] in selected_assets
    ]

    st.caption(f"Showing {len(filtered)} of {len(evidence)} evidence item(s).")

    for item in filtered:
        st.markdown(f"**[{item['category']}]** {item['statement']}")
        st.caption(
            f"Source: {item['source_filename']} · asset_id={item['asset_id']} · "
            f"processing_result_id={item['processing_result_id']}"
        )
        if item.get("excerpt"):
            st.code(item["excerpt"], language=None)
        st.markdown("---")


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------

st.title("Resonance")
st.caption("Multimodal Experience Intelligence")

st.subheader("Backend status")
health_resp = api_get("/health", timeout=3)
if health_resp is not None and health_resp.status_code == 200:
    st.success(f"Backend is healthy: {health_resp.json()}")
elif health_resp is not None:
    st.error(f"Backend returned status {health_resp.status_code}")
else:
    st.error(f"Could not reach backend at {BACKEND_URL}.")

st.divider()
active_project = render_project_picker()

if active_project:
    st.divider()
    project_id = active_project["id"]

    overview_resp = api_get(f"/projects/{project_id}/overview")
    overview = overview_resp.json() if overview_resp is not None and overview_resp.status_code == 200 else None

    if overview and overview.get("active_provider") == "mock":
        st.info(
            "🧪 **Mock mode active** — MockAIProvider is generating all AI-derived content "
            "(themes, sentiment, questionnaire, report) as deterministic placeholder output. "
            "This demonstrates the full architecture end-to-end; it is not a real AI/ML analysis."
        )
    elif overview and overview.get("latest_intelligence_id") is None:
        st.caption("AI provider not yet determined for this project — will default to MockAIProvider.")

    tab_overview, tab_assets, tab_intelligence, tab_questionnaire, tab_report, tab_evidence = st.tabs(
        ["Overview", "Assets", "Intelligence", "Questionnaire", "Executive Report", "Evidence"]
    )
    with tab_overview:
        render_overview_tab(active_project, overview)
    with tab_assets:
        render_assets_tab(active_project)
    with tab_intelligence:
        render_intelligence_tab(active_project)
    with tab_questionnaire:
        render_questionnaire_tab(active_project)
    with tab_report:
        render_report_tab(active_project)
    with tab_evidence:
        render_evidence_tab(active_project)
else:
    st.info("Create or select a project above to begin.")
