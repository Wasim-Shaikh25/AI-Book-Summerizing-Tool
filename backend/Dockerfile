# syntax=docker/dockerfile:1
FROM python:3.11-slim

# System dependencies:
# - tesseract-ocr + eng data: OCR stage for scanned PDFs
# - poppler-utils: PDF rasterization fallbacks
# - libgl1 / libglib2.0-0: OpenCV/Pillow runtime deps used by layout + OCR
# - curl: container healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-eng \
    poppler-utils \
    libgl1 \
    libglib2.0-0 \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Cache models inside the image layer dir; mounted volume overrides in compose.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    HF_HOME=/app/.cache/huggingface

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Run as a non-root user (security: never run app as root).
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /workspace/output /workspace/logs /app/.cache \
    && chown -R appuser:appuser /app /workspace
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -fsS http://localhost:8000/api/health || exit 1

# Workers are configurable via UVICORN_WORKERS (default 1 for dev parity).
CMD ["sh", "-c", "uvicorn api.main:app --host 0.0.0.0 --port 8000 --workers ${UVICORN_WORKERS:-1}"]
