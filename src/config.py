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
# Back-compat:
#   - ACTIVE_MODEL (older name)
LLM_PROVIDER = (
    os.getenv("LLM_PROVIDER")
    or _load_dotenv_value("LLM_PROVIDER")
    or os.getenv("ACTIVE_MODEL")
    or _load_dotenv_value("ACTIVE_MODEL")
    or "OLLAMA"
).strip().upper()

# Backwards compatible alias (do not use in new code)
ACTIVE_MODEL = LLM_PROVIDER

# Global debug flag for structural pipeline tracing
DEBUG_STRUCTURE = True

# Provider configuration (centralized; providers should not call os.getenv directly)

# Gemini
GEMINI_API_KEY = (
    os.getenv("GEMINI_API_KEY")
    or os.getenv("GOOGLE_API_KEY")
    or _load_dotenv_value("GEMINI_API_KEY")
    or _load_dotenv_value("GOOGLE_API_KEY")
    or ""
)
GEMINI_MODEL = os.getenv("GEMINI_MODEL") or _load_dotenv_value("GEMINI_MODEL") or "models/gemini-3.1-flash-lite-preview"

# OpenAI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or _load_dotenv_value("OPENAI_API_KEY") or ""
OPENAI_MODEL = os.getenv("OPENAI_MODEL") or _load_dotenv_value("OPENAI_MODEL") or "gpt-4o-mini"
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL") or _load_dotenv_value("OPENAI_BASE_URL") or "https://api.openai.com"

# Ollama
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL") or _load_dotenv_value("OLLAMA_BASE_URL") or "http://localhost:11434"
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL") or _load_dotenv_value("OLLAMA_MODEL") or "llama3.2:3b"
OLLAMA_TIMEOUT_S = float(os.getenv("OLLAMA_TIMEOUT_S") or _load_dotenv_value("OLLAMA_TIMEOUT_S") or "600")
OLLAMA_NUM_PREDICT = int(os.getenv("OLLAMA_NUM_PREDICT") or _load_dotenv_value("OLLAMA_NUM_PREDICT") or "96")
OLLAMA_HTTP_DEBUG = (os.getenv("OLLAMA_HTTP_DEBUG") or _load_dotenv_value("OLLAMA_HTTP_DEBUG") or "0").strip().lower() in {"1", "true", "yes", "y", "on"}
OLLAMA_HTTP_DEBUG_MAX_CHARS = int(os.getenv("OLLAMA_HTTP_DEBUG_MAX_CHARS") or _load_dotenv_value("OLLAMA_HTTP_DEBUG_MAX_CHARS") or "4000")

# Pipeline batch sizing (applies to all providers)
LLM_VALIDITY_BATCH_SIZE = int(os.getenv("LLM_VALIDITY_BATCH_SIZE") or _load_dotenv_value("LLM_VALIDITY_BATCH_SIZE") or "20")
LLM_TOC_BATCH_SIZE = int(os.getenv("LLM_TOC_BATCH_SIZE") or _load_dotenv_value("LLM_TOC_BATCH_SIZE") or "20")

# Token limits for summarization (reverted to chunk-by-chunk focus)
REWRITE_MAX_TOKENS = 15000  # Increased to allow for more content expansion
