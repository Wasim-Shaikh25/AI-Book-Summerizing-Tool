# AI Notes Creator

PDF book structure extraction, AI note generation, and web chat with Word export.

## Repository layout

| Path | Purpose |
|------|---------|
| [`backend/`](./backend/README.md) | **All Python** — engine, API, CLI, tests, scripts |
| `backend/engine/`, `backend/web_platform/`, `backend/app/` | Import shims (incremental rename targets) |
| [`frontend/`](./frontend/) | React web UI |
| [`specs/`](./specs/) | Requirements and SDD |
| `logs/`, `output/`, `models/`, `pdfs/` | Runtime data at repo root (gitignored) |
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

Open http://localhost:5173. Set `AUTH_ENABLED=false` for local dev without OAuth,
or keep `ALLOW_GUEST=true` to offer a **"Continue as guest"** button (each guest
gets an isolated, persisted account + short-lived session token). Configure OAuth
in `.env` for full login (see `.env.example`).

### Docker

```bash
# Local development (hot reload): frontend :5173, api :8000
cp .env.example .env        # fill an LLM key
docker compose up --build

# Production (nginx + uvicorn workers, durable named volumes): app on :80
cp .env.prod.example .env   # fill real secrets (JWT_SECRET, LLM key, URLs)
docker compose -f docker-compose.prod.yml up -d --build
```

Full deployment guide (env profiles, storage volumes, CORS, healthchecks):
[`specs/deployment.md`](./specs/deployment.md).

### Tests

```bash
cd backend && pytest
```

## Specs

Start at [`specs/index.md`](./specs/index.md) or [`specs/requirements-web-platform.md`](./specs/requirements-web-platform.md).
Deployment: [`specs/deployment.md`](./specs/deployment.md).
