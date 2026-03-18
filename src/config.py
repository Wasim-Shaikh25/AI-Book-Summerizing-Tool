import os

# Define the base directory of the project
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Define paths for PDF and output folders
PDF_FOLDER = os.path.join(BASE_DIR, "pdfs")
OUTPUT_FOLDER = os.path.join(BASE_DIR, "output")
REFERENCE_DOCX_PATH = os.path.join(BASE_DIR, "reference.docx")

# Ensure output folder exists
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# Configuration for chunking
CHUNK_SIZE_WORDS = 1500
CHUNK_OVERLAP_WORDS = 150

# Active model for LLM calls (TOC / validation / rewrite). Supported: "GEMINI", "OLLAMA"
ACTIVE_MODEL = "OLLAMA"

# Global debug flag for structural pipeline tracing
DEBUG_STRUCTURE = True

# Embedding model for FAISS (using Universal Sentence Encoder)
# EMBEDDING_MODEL is no longer directly used as we are loading the model via tensorflow_hub

# Gemini configuration
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


GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or _load_dotenv_value("GEMINI_API_KEY") or _load_dotenv_value("GOOGLE_API_KEY") or ""
# Use a stable, widely available model by default.
# google.genai expects full model id like "gemini-1.5-flash" (no "models/" prefix).
# Use a stable, widely available model by default.
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "models/gemini-3.1-flash-lite-preview")

# Token limits for summarization (reverted to chunk-by-chunk focus)
REWRITE_MAX_TOKENS = 15000 # Increased to allow for more content expansion
# Deprecated token limits (removed as per new requirements)
# CORE_IDEAS_MAX_TOKENS = 4000
# MASTER_SUMMARY_MAX_TOKENS = 4000
# TOPIC_CANONICAL_MAX_TOKENS = 2000
# FACT_EXTRACTION_MAX_TOKENS = 2000
# TOPIC_REWRITE_MAX_TOKENS = 10000
# OUTLINE_PLANNING_MAX_TOKENS = 4000
# SINGLE_PASS_WRITING_MAX_TOKENS = 30000
