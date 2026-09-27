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
            st.success(f"Uploaded {len(results)} file(s).")
            st.table(results)
else:
    st.info("Create or load a project to upload files.")
