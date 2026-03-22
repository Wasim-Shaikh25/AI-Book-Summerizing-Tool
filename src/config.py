import os

# Define the base directory of the project
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def _load_dotenv_value(key: str) -> str:
    """
    Minimal .env loader (no external deps).
    Loads the first matching KEY=... line from a `.env` file at project root.
    """
    try:
        env_path = os.path.join(BASE_DIR, ".env")
        if not os.path.exists(env_path):
            return ""
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if not s or s.startswith("#") or "=" not in s:
                    continue
                k, v = s.split("=", 1)
                if k.strip() != key:
                    continue
                v = v.strip().strip('"').strip("'")
                return v
    except Exception:
        return ""
    return ""

# Define paths for PDF and output folders
PDF_FOLDER = os.path.join(BASE_DIR, "pdfs")
OUTPUT_FOLDER = os.path.join(BASE_DIR, "output")
REFERENCE_DOCX_PATH = os.path.join(BASE_DIR, "reference.docx")

# Ensure output folder exists
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# Configuration for chunking
CHUNK_SIZE_WORDS = 1500
CHUNK_OVERLAP_WORDS = 150

# Active provider for LLM calls (TOC / validation / rewrite).
# Supported: "GEMINI", "OLLAMA", "OPENAI"
#
# Env vars (preferred):
#   - LLM_PROVIDER=OLLAMA|GEMINI|OPENAI
#
LLM_PROVIDER = (
    os.getenv("LLM_PROVIDER")
    or _load_dotenv_value("LLM_PROVIDER")
    or "OLLAMA"
).strip().upper()

# Global debug flag for structural pipeline tracing
DEBUG_STRUCTURE = True

# Provider configuration (centralized; providers should not call os.getenv directly)
#
# Generic LLM_* keys (apply to all providers)
# - Providers may also support provider-specific override keys; those take precedence.
# - If provider-specific key is not set, the provider falls back to LLM_*.
#
# Supported generic keys:
#   - LLM_PROVIDER=OLLAMA|GEMINI|OPENAI
#   - LLM_MODEL=...
#   - LLM_BASE_URL=...
#   - LLM_TIMEOUT_S=...
#   - LLM_HTTP_DEBUG=0/1 (debug request/response logging)
#   - LLM_HTTP_DEBUG_MAX_CHARS=...
#
# Batch sizing keys (apply to all providers):
#   - LLM_VALIDITY_BATCH_SIZE
#   - LLM_TOC_BATCH_SIZE

# Generic LLM_* defaults (can be used by all providers)
LLM_MODEL = os.getenv("LLM_MODEL") or _load_dotenv_value("LLM_MODEL") or ""
LLM_BASE_URL = os.getenv("LLM_BASE_URL") or _load_dotenv_value("LLM_BASE_URL") or ""
LLM_TIMEOUT_S = float(os.getenv("LLM_TIMEOUT_S") or _load_dotenv_value("LLM_TIMEOUT_S") or "600")
LLM_HTTP_DEBUG = (os.getenv("LLM_HTTP_DEBUG") or _load_dotenv_value("LLM_HTTP_DEBUG") or "0").strip().lower() in {
    "1",
    "true",
    "yes",
    "y",
    "on",
}
LLM_HTTP_DEBUG_MAX_CHARS = int(os.getenv("LLM_HTTP_DEBUG_MAX_CHARS") or _load_dotenv_value("LLM_HTTP_DEBUG_MAX_CHARS") or "4000")

# Gemini (provider-specific overrides)
GEMINI_API_KEY = (
    os.getenv("GEMINI_API_KEY")
    or os.getenv("GOOGLE_API_KEY")
    or _load_dotenv_value("GEMINI_API_KEY")
    or _load_dotenv_value("GOOGLE_API_KEY")
    or ""
)
GEMINI_MODEL = os.getenv("GEMINI_MODEL") or _load_dotenv_value("GEMINI_MODEL") or LLM_MODEL or "models/gemini-3.1-flash-lite-preview"
GEMINI_TIMEOUT_S = float(os.getenv("GEMINI_TIMEOUT_S") or _load_dotenv_value("GEMINI_TIMEOUT_S") or str(LLM_TIMEOUT_S) or "600")

# OpenAI (provider-specific overrides)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or _load_dotenv_value("OPENAI_API_KEY") or ""
OPENAI_MODEL = os.getenv("OPENAI_MODEL") or _load_dotenv_value("OPENAI_MODEL") or LLM_MODEL or "gpt-4o-mini"
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL") or _load_dotenv_value("OPENAI_BASE_URL") or LLM_BASE_URL or "https://api.openai.com"
OPENAI_TIMEOUT_S = float(os.getenv("OPENAI_TIMEOUT_S") or _load_dotenv_value("OPENAI_TIMEOUT_S") or str(LLM_TIMEOUT_S) or "600")

# Ollama (provider-specific overrides)
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL") or _load_dotenv_value("OLLAMA_BASE_URL") or LLM_BASE_URL or "http://localhost:11434"
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL") or _load_dotenv_value("OLLAMA_MODEL") or LLM_MODEL or "llama3.2:3b"
OLLAMA_TIMEOUT_S = float(os.getenv("OLLAMA_TIMEOUT_S") or _load_dotenv_value("OLLAMA_TIMEOUT_S") or str(LLM_TIMEOUT_S) or "600")

# Ollama-only tuning knobs (true provider-specific features)
OLLAMA_NUM_PREDICT = int(os.getenv("OLLAMA_NUM_PREDICT") or _load_dotenv_value("OLLAMA_NUM_PREDICT") or "96")

# Pipeline batch sizing (applies to all providers)
LLM_VALIDITY_BATCH_SIZE = int(os.getenv("LLM_VALIDITY_BATCH_SIZE") or _load_dotenv_value("LLM_VALIDITY_BATCH_SIZE") or "20")
LLM_TOC_BATCH_SIZE = int(os.getenv("LLM_TOC_BATCH_SIZE") or _load_dotenv_value("LLM_TOC_BATCH_SIZE") or "20")

# Token limits for summarization (reverted to chunk-by-chunk focus)
REWRITE_MAX_TOKENS = 15000  # Increased to allow for more content expansion
