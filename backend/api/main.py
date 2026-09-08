"""FastAPI application entry point."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

_backend_root = Path(__file__).resolve().parents[1]
_project_root = Path(os.getenv("PROJECT_ROOT", str(_backend_root.parent)))
load_dotenv(_project_root / ".env")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Import orchestration tool modules to auto-register tools in global registry
from src.modules.orchestration import batch_tools, corpus_tools, extraction_tools, read_tools, write_tools

from api.routes import auth, books, chat, exports, jobs, research, search
from auth.config import get_auth_settings
from middleware.rate_limit import RateLimitMiddleware

app = FastAPI(
    title="InsightEngine API",
    description="AI Document Research Engine — corpus search, agentic workflows, and verified citations",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_auth_settings().cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RateLimitMiddleware)

app.include_router(auth.router, prefix="/api")
app.include_router(books.router, prefix="/api")
app.include_router(chat.router, prefix="/api")
app.include_router(exports.router, prefix="/api")
app.include_router(search.router, prefix="/api")
app.include_router(research.router, prefix="/api")
app.include_router(jobs.router, prefix="/api")


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "insightengine-api"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=True)
