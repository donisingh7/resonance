# Resonance — Multimodal Experience Intelligence

Clean-room project foundation. Backend (FastAPI) + frontend (Streamlit).

## Structure

```
resonance/
├── backend/
│   └── app/
│       ├── main.py          # FastAPI app entrypoint
│       ├── api/              # route modules (health, future endpoints)
│       ├── core/             # config/settings
│       ├── models/           # future data models
│       └── services/         # future processing logic
├── frontend/
│   └── app.py                # Streamlit UI
├── requirements.txt
├── .env.example
└── .gitignore
```

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
copy .env.example .env
```

## Run backend

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

## Run frontend

```bash
cd frontend
streamlit run app.py
```

Backend health check: http://localhost:8000/health
