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

# Active model for LLM calls (TOC / validation / rewrite). Supported: "GEMINI", "OLLAMA", "OPENAI"
ACTIVE_MODEL = os.getenv("ACTIVE_MODEL") or _load_dotenv_value("ACTIVE_MODEL") or "OLLAMA"

# Global debug flag for structural pipeline tracing
DEBUG_STRUCTURE = True

# Gemini configuration
GEMINI_API_KEY = (
    os.getenv("GEMINI_API_KEY")
    or os.getenv("GOOGLE_API_KEY")
    or _load_dotenv_value("GEMINI_API_KEY")
    or _load_dotenv_value("GOOGLE_API_KEY")
    or ""
)
# Use a stable, widely available model by default.
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "models/gemini-3.1-flash-lite-preview")

# OpenAI configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or _load_dotenv_value("OPENAI_API_KEY") or ""
OPENAI_MODEL = os.getenv("OPENAI_MODEL") or _load_dotenv_value("OPENAI_MODEL") or "gpt-4o-mini"
# Optional: for proxies / gateways / local emulators.
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL") or _load_dotenv_value("OPENAI_BASE_URL") or "https://api.openai.com"

# Token limits for summarization (reverted to chunk-by-chunk focus)
REWRITE_MAX_TOKENS = 15000  # Increased to allow for more content expansion
