# AI Notes Creator — Backend

Self-contained Python application: PDF pipeline engine, CLI, REST API, OAuth, and tests.

## Layout

```
backend/
├── api/           # FastAPI routes
├── auth/          # OAuth + JWT
├── services/      # Chat, ingestion, export policy
├── storage/       # User/conversation DB repos
├── src/           # Core engine (modules/, shared/, utils/)
├── tests/         # Unit + integration tests
├── scripts/       # Pipeline utilities
├── config/        # default.yaml tunables
├── main.py        # CLI entry
└── requirements.txt
```

Runtime data (output, models, pdfs) lives at **repo root** (`../output`, `../models`, `../pdfs`).  
Secrets: repo root `.env`.

## Commands (run from `backend/`)

```bash
pip install -r requirements.txt

# CLI
python main.py

# Web API
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

# Tests
pytest
```

From repo root:

```bash
cd backend && pytest
cd backend && python main.py
```

Set `PROJECT_ROOT` if data lives outside the default parent folder (e.g. Docker).
