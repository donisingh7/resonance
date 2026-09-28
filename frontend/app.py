import os

import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

st.set_page_config(page_title="Resonance")

st.title("Resonance")
st.caption("Multimodal Experience Intelligence")

st.subheader("Backend status")
try:
    response = requests.get(f"{BACKEND_URL}/health", timeout=3)
    if response.status_code == 200:
        st.success(f"Backend is healthy: {response.json()}")
    else:
        st.error(f"Backend returned status {response.status_code}")
except requests.exceptions.RequestException as exc:
    st.error(f"Could not reach backend: {exc}")

st.divider()
st.subheader("Create a project")

with st.form("create_project_form"):
    project_name = st.text_input("Name")
    project_description = st.text_area("Description")
    submitted = st.form_submit_button("Create project")

    if submitted:
        if not project_name.strip():
            st.warning("Name is required.")
        else:
            try:
                resp = requests.post(
                    f"{BACKEND_URL}/projects",
                    json={"name": project_name, "description": project_description},
                    timeout=5,
                )
                if resp.status_code == 200:
                    project = resp.json()
                    st.session_state["active_project"] = project
                    st.success(f"Project created: {project['id']}")
                else:
                    st.error(f"Failed to create project: {resp.status_code} {resp.text}")
            except requests.exceptions.RequestException as exc:
                st.error(f"Could not reach backend: {exc}")

st.divider()
st.subheader("Active project")

active_project = st.session_state.get("active_project")

project_id_input = st.text_input(
    "Project ID",
    value=active_project["id"] if active_project else "",
    help="Enter a project ID or create one above",
)

if st.button("Load project"):
    try:
        resp = requests.get(f"{BACKEND_URL}/projects/{project_id_input}", timeout=5)
        if resp.status_code == 200:
            active_project = resp.json()
            st.session_state["active_project"] = active_project
        else:
            st.error(f"Failed to load project: {resp.status_code} {resp.text}")
    except requests.exceptions.RequestException as exc:
        st.error(f"Could not reach backend: {exc}")

if active_project:
    st.json(active_project)

    st.subheader("Upload files")
    uploaded_files = st.file_uploader(
        "Supported: mp3, wav, mp4, jpg, jpeg, png, pdf, txt",
        accept_multiple_files=True,
    )

    if uploaded_files and st.button("Upload selected files"):
        results = []
        for uploaded_file in uploaded_files:
            try:
                resp = requests.post(
                    f"{BACKEND_URL}/projects/{active_project['id']}/upload",
                    files={"file": (uploaded_file.name, uploaded_file.getvalue())},
                    timeout=30,
                )
                if resp.status_code == 200:
                    results.append(resp.json())
                else:
                    st.error(f"{uploaded_file.name}: {resp.status_code} {resp.text}")
            except requests.exceptions.RequestException as exc:
                st.error(f"{uploaded_file.name}: could not reach backend: {exc}")

        if results:
            st.success(f"Uploaded and ingested {len(results)} file(s).")

    st.subheader("Ingested assets")
    st.button("Refresh assets")  # click alone triggers a rerun, which re-fetches below

    try:
        assets_resp = requests.get(
            f"{BACKEND_URL}/projects/{active_project['id']}/assets", timeout=5
        )
    except requests.exceptions.RequestException as exc:
        assets_resp = None
        st.error(f"Could not reach backend: {exc}")

    try:
        results_resp = requests.get(
            f"{BACKEND_URL}/projects/{active_project['id']}/processing-results", timeout=5
        )
        results_by_asset = (
            {r["asset_id"]: r for r in results_resp.json()}
            if results_resp is not None and results_resp.status_code == 200
            else {}
        )
    except requests.exceptions.RequestException:
        results_by_asset = {}

    if assets_resp is not None:
        if assets_resp.status_code == 200:
            assets = assets_resp.json()
            if not assets:
                st.info("No assets ingested yet for this project.")

            for asset in assets:
                result = results_by_asset.get(asset["id"])
                status_label = result["status"] if result else "not processed"

                with st.expander(
                    f"{asset['original_filename']} — {asset['modality']} — {status_label}"
                ):
                    st.caption(
                        f"mime: {asset['mime_type']} · size: {asset['size_bytes']} bytes · "
                        f"ingestion: {asset['ingestion_status']}"
                    )
                    st.json(asset["technical_metadata"])

                    if st.button("Process asset", key=f"process_{asset['id']}"):
                        try:
                            process_resp = requests.post(
                                f"{BACKEND_URL}/projects/{active_project['id']}"
                                f"/assets/{asset['id']}/process",
                                timeout=120,
                            )
                            if process_resp.status_code == 200:
                                st.success("Processing complete.")
                                st.rerun()
                            else:
                                st.error(
                                    f"Processing failed: "
                                    f"{process_resp.status_code} {process_resp.text}"
                                )
                        except requests.exceptions.RequestException as exc:
                            st.error(f"Could not reach backend: {exc}")

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
        else:
            st.error(f"Failed to load assets: {assets_resp.status_code} {assets_resp.text}")

    st.divider()
    st.subheader("Project intelligence")

    if assets_resp is not None and assets_resp.status_code == 200:
        assets = assets_resp.json()
        completed_count = sum(
            1 for r in results_by_asset.values() if r.get("status") == "completed"
        )
        st.caption(
            f"{len(assets)} asset(s) ingested · {completed_count} with a completed "
            f"processing result."
        )

    if st.button("Generate Project Intelligence"):
        try:
            gen_resp = requests.post(
                f"{BACKEND_URL}/projects/{active_project['id']}/intelligence",
                json={},
                timeout=60,
            )
            if gen_resp.status_code == 200:
                st.success("Project intelligence generated.")
                st.rerun()
            else:
                st.error(f"Generation failed: {gen_resp.status_code} {gen_resp.text}")
        except requests.exceptions.RequestException as exc:
            st.error(f"Could not reach backend: {exc}")

    try:
        intel_resp = requests.get(
            f"{BACKEND_URL}/projects/{active_project['id']}/intelligence", timeout=5
        )
    except requests.exceptions.RequestException as exc:
        intel_resp = None
        st.error(f"Could not reach backend: {exc}")

    if intel_resp is not None:
        if intel_resp.status_code == 200:
            intelligence_records = intel_resp.json()
            if not intelligence_records:
                st.info("No project intelligence generated yet.")
            else:
                intelligence_records = sorted(
                    intelligence_records, key=lambda r: r["created_at"], reverse=True
                )
                for record in intelligence_records:
                    label = f"{record['provider']} — {record['status']} — {record['created_at']}"
                    with st.expander(label, expanded=(record is intelligence_records[0])):
                        if record["status"] == "failed":
                            st.error(f"Intelligence generation error: {record['error']}")
                            continue

                        if record["provider"] == "mock":
                            st.caption(
                                "MockAIProvider output: deterministic placeholder synthesis "
                                "for architecture/flow verification, not real AI analysis."
                            )

                        st.markdown("**Summary**")
                        st.write(record["summary"])

                        col1, col2 = st.columns(2)
                        with col1:
                            st.markdown("**Top themes**")
                            for item in record["top_themes"]:
                                st.write(f"- {item}")
                            st.markdown("**Pain points**")
                            for item in record["pain_points"]:
                                st.write(f"- {item}")
                            st.markdown("**Opportunities**")
                            for item in record["opportunities"]:
                                st.write(f"- {item}")
                        with col2:
                            st.markdown("**Sentiment summary**")
                            st.write(record["sentiment_summary"])
                            st.markdown("**Positive signals**")
                            for item in record["positive_signals"]:
                                st.write(f"- {item}")
                            st.markdown("**Recommended actions**")
                            for item in record["recommended_actions"]:
                                st.write(f"- {item}")

                        st.markdown("**Questions / concerns**")
                        for item in record["questions_or_concerns"]:
                            st.write(f"- {item}")

                        st.markdown(f"**Evidence** ({len(record['evidence'])} item(s))")
                        for evidence_item in record["evidence"]:
                            st.markdown(
                                f"- **[{evidence_item['category']}]** {evidence_item['statement']}"
                            )
                            st.caption(
                                f"Source: {evidence_item['source_filename']} · "
                                f"asset_id={evidence_item['asset_id']} · "
                                f"processing_result_id={evidence_item['processing_result_id']}"
                            )
                            if evidence_item.get("excerpt"):
                                st.code(evidence_item["excerpt"], language=None)

                        st.caption(
                            f"Source processing results: "
                            f"{', '.join(record['source_result_ids']) or 'none'}"
                        )
        else:
            st.error(f"Failed to load project intelligence: {intel_resp.status_code} {intel_resp.text}")

    st.divider()
    st.subheader("Follow-up questionnaire")

    if st.button("Generate follow-up questionnaire"):
        try:
            qgen_resp = requests.post(
                f"{BACKEND_URL}/projects/{active_project['id']}/questionnaires",
                json={},
                timeout=30,
            )
            if qgen_resp.status_code == 200:
                st.success("Questionnaire generated.")
                st.rerun()
            elif qgen_resp.status_code == 400:
                st.warning(qgen_resp.json().get("detail", "Generation failed."))
            else:
                st.error(f"Generation failed: {qgen_resp.status_code} {qgen_resp.text}")
        except requests.exceptions.RequestException as exc:
            st.error(f"Could not reach backend: {exc}")

    try:
        questionnaires_resp = requests.get(
            f"{BACKEND_URL}/projects/{active_project['id']}/questionnaires", timeout=5
        )
    except requests.exceptions.RequestException as exc:
        questionnaires_resp = None
        st.error(f"Could not reach backend: {exc}")

    question_type_options = ["likert", "multiple_choice", "free_text", "yes_no"]

    if questionnaires_resp is not None:
        if questionnaires_resp.status_code == 200:
            questionnaires = questionnaires_resp.json()
            if not questionnaires:
                st.info("No questionnaire generated yet.")
            else:
                questionnaires = sorted(
                    questionnaires, key=lambda q: q["created_at"], reverse=True
                )
                for q in questionnaires:
                    label = f"{q['provider']} — {q['status']} — {len(q['questions'])} question(s) — {q['created_at']}"
                    with st.expander(label, expanded=(q is questionnaires[0])):
                        if q["status"] == "failed":
                            st.error(f"Questionnaire generation error: {q['error']}")
                            continue

                        if q["provider"] == "mock":
                            st.caption(
                                "MockAIProvider output: deterministic follow-up questions "
                                "derived from mock project intelligence, not real AI-generated "
                                "questions."
                            )

                        with st.form(f"edit_questionnaire_{q['id']}"):
                            edited_questions = []
                            for question in q["questions"]:
                                st.markdown(f"**Question `{question['id'][:8]}`**")
                                text = st.text_area(
                                    "Text",
                                    value=question["text"],
                                    key=f"text_{question['id']}",
                                )
                                qtype = st.selectbox(
                                    "Type",
                                    question_type_options,
                                    index=question_type_options.index(question["question_type"]),
                                    key=f"type_{question['id']}",
                                )
                                required = st.checkbox(
                                    "Required",
                                    value=question["required"],
                                    key=f"required_{question['id']}",
                                )
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
                                try:
                                    save_resp = requests.put(
                                        f"{BACKEND_URL}/projects/{active_project['id']}"
                                        f"/questionnaires/{q['id']}",
                                        json={"questions": edited_questions},
                                        timeout=15,
                                    )
                                    if save_resp.status_code == 200:
                                        st.success("Questionnaire saved.")
                                        st.rerun()
                                    else:
                                        st.error(
                                            f"Save failed: {save_resp.status_code} {save_resp.text}"
                                        )
                                except requests.exceptions.RequestException as exc:
                                    st.error(f"Could not reach backend: {exc}")
        else:
            st.error(
                f"Failed to load questionnaires: "
                f"{questionnaires_resp.status_code} {questionnaires_resp.text}"
            )

    st.divider()
    st.subheader("Executive report")

    if st.button("Generate executive report"):
        try:
            rgen_resp = requests.post(
                f"{BACKEND_URL}/projects/{active_project['id']}/reports",
                json={},
                timeout=60,
            )
            if rgen_resp.status_code == 200:
                st.success("Executive report generated.")
                st.rerun()
            elif rgen_resp.status_code == 400:
                st.warning(rgen_resp.json().get("detail", "Generation failed."))
            else:
                st.error(f"Generation failed: {rgen_resp.status_code} {rgen_resp.text}")
        except requests.exceptions.RequestException as exc:
            st.error(f"Could not reach backend: {exc}")

    try:
        reports_resp = requests.get(
            f"{BACKEND_URL}/projects/{active_project['id']}/reports", timeout=5
        )
    except requests.exceptions.RequestException as exc:
        reports_resp = None
        st.error(f"Could not reach backend: {exc}")

    severity_display = {"critical": "error", "warning": "warning", "info": "info"}

    if reports_resp is not None:
        if reports_resp.status_code == 200:
            reports = reports_resp.json()
            if not reports:
                st.info("No executive report generated yet.")
            else:
                reports = sorted(reports, key=lambda r: r["created_at"], reverse=True)
                for rep in reports:
                    label = f"{rep['provider']} — {rep['status']} — {rep['created_at']}"
                    with st.expander(label, expanded=(rep is reports[0])):
                        if rep["provider"] == "mock":
                            st.caption(
                                "MockAIProvider output: this entire report is built from "
                                "deterministic mock project intelligence, not real AI analysis."
                            )

                        if rep.get("pdf_path"):
                            st.link_button(
                                "Download PDF",
                                url=f"{BACKEND_URL}/projects/{active_project['id']}"
                                f"/reports/{rep['id']}/pdf",
                            )
                        else:
                            st.caption("PDF not available for this report.")

                        st.markdown("**Risk / data-quality flags**")
                        if not rep["risk_flags"]:
                            st.write("No flags raised.")
                        for flag in rep["risk_flags"]:
                            display_fn = getattr(st, severity_display.get(flag["severity"], "info"))
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
                                f"Questionnaire `{qs['questionnaire_id']}` — "
                                f"{qs['question_count']} question(s), status: {qs['status']}."
                            )
                        else:
                            st.write("No questionnaire was generated for this analysis.")

                        st.markdown(f"**Supporting evidence** ({len(rep['evidence'])} item(s))")
                        for evidence_item in rep["evidence"]:
                            st.markdown(
                                f"- **[{evidence_item['category']}]** {evidence_item['statement']}"
                            )
                            st.caption(
                                f"Source: {evidence_item['source_filename']} · "
                                f"asset_id={evidence_item['asset_id']} · "
                                f"processing_result_id={evidence_item['processing_result_id']}"
                            )
                            if evidence_item.get("excerpt"):
                                st.code(evidence_item["excerpt"], language=None)
        else:
            st.error(f"Failed to load reports: {reports_resp.status_code} {reports_resp.text}")
else:
    st.info("Create or load a project to upload files.")
