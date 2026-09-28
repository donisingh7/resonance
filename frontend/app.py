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
else:
    st.info("Create or load a project to upload files.")
