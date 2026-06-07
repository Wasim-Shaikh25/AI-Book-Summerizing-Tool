# AI Notes Creator

PDF book structure extraction, AI note generation, and web chat with Word export.

## Repository layout

| Path | Purpose |
|------|---------|
| [`backend/`](./backend/README.md) | **All Python** — engine, API, CLI, tests, scripts |
| [`frontend/`](./frontend/) | React web UI |
| [`specs/`](./specs/) | Requirements and SDD |
| `output/`, `models/`, `pdfs/` | Runtime data (gitignored) |
| `.env` | Secrets (copy from `.env.example`) |

## Quick start

### Backend (CLI)

```bash
cd backend
pip install -r requirements.txt
python main.py
```

### Backend (API) + Frontend

```bash
# Terminal 1
cd backend
uvicorn api.main:app --reload --port 8000

# Terminal 2
cd frontend
npm install && npm run dev
```

Open http://localhost:5173 — configure OAuth in `.env` (see `.env.example`).

### Docker

```bash
docker compose up --build
```

### Tests

```bash
cd backend && pytest
```

## Specs

Start at [`specs/index.md`](./specs/index.md) or [`specs/requirements-web-platform.md`](./specs/requirements-web-platform.md).
