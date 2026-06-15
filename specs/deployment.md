# Deployment

Status: **Implemented** (Docker dev + prod stacks). Kubernetes/cloud-managed
storage are **Planned** and out of scope here.

## Environments

| Profile | Compose file | Frontend | Backend | Source mount | Data |
|---|---|---|---|---|---|
| **local / dev** | `docker-compose.yml` | Vite dev server (`:5173`, hot reload) | uvicorn `--reload` (`:8000`) | repo bind-mounted | host repo `output/`, `logs/` |
| **prod** | `docker-compose.prod.yml` | nginx static + `/api` proxy (`:80`) | uvicorn `--workers` (internal `:8000`) | none (built image) | named volumes |

Config overlay order (later wins): `backend/config/default.yaml` → system env → `.env`.

## Env files

- `.env.example` — full reference of every key (copy to `.env` for dev).
- `.env.prod.example` — only the keys that change for a hardened prod deploy.
- Real `.env`, `.env.dev`, `.env.prod` are git-ignored (contain secrets).

Production must set: `JWT_SECRET` (random), `LLM_PROVIDER` + API key,
`FRONTEND_URL`/`API_BASE_URL` (public HTTPS), and OAuth creds if `AUTH_ENABLED=true`.

## Run

```bash
# Local development (hot reload)
cp .env.example .env          # fill LLM key
docker compose up --build
# frontend http://localhost:5173  |  api http://localhost:8000/api/health

# Production
cp .env.prod.example .env     # fill real secrets
docker compose -f docker-compose.prod.yml up -d --build
# app served on http://<host>/  (nginx proxies /api -> backend)
```

## Storage strategy

Persistent data lives under `PROJECT_ROOT` (set to `/workspace` in containers):

| Volume | Path | Contents |
|---|---|---|
| `notes_output` | `/workspace/output` | `knowledge_base.db` (users, conversations, books), `exports/` (.docx), `uploads/` (source PDFs), `rag_index/` (FAISS) |
| `notes_logs` | `/workspace/logs` | pipeline stage artifacts (`s01`–`s16`), app logs |
| `notes_models` | `/workspace/models` | downloaded transformer / cross-encoder weights |
| `hf_cache` | `/app/.cache/huggingface` | HuggingFace download cache |

In **dev**, these map to the host repo via the bind mount, so output is
directly inspectable. In **prod**, they are Docker named volumes — back them up
(`docker run --rm -v notes_output:/data -v $PWD:/backup alpine tar czf /backup/output.tgz /data`)
to retain user data across redeploys.

## CORS / networking

- `CORSMiddleware` origins come from `AuthSettings.cors_origins`: localhost dev
  hosts + `FRONTEND_URL` + comma-separated `CORS_EXTRA_ORIGINS`.
- In prod the SPA is same-origin (nginx serves the build and proxies `/api`), so
  CORS is effectively a no-op; set `FRONTEND_URL` for OAuth redirects.
- nginx disables proxy buffering on `/api/` for SSE chat streaming and allows
  120 MB bodies (matches `MAX_UPLOAD_MB`).

## Health & robustness

- Backend: `GET /api/health`; Docker `HEALTHCHECK` curls it. Prod frontend waits
  on `service_healthy` before starting.
- Both services run `restart: unless-stopped` in prod.
- Backend image runs as non-root user `appuser` (uid 10001).
- Images exclude secrets and runtime data via `.dockerignore`.

## System dependencies (baked into backend image)

`tesseract-ocr` + `tesseract-ocr-eng` (OCR), `poppler-utils` (PDF raster),
`libgl1`/`libglib2.0-0` (OpenCV/Pillow), `curl` (healthcheck).
