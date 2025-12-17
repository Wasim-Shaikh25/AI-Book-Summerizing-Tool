import os

# Define the base directory of the project
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Define paths for PDF and output folders
PDF_FOLDER = os.path.join(BASE_DIR, "pdfs")
OUTPUT_FOLDER = os.path.join(BASE_DIR, "output")
REFERENCE_DOCX_PATH = os.path.join(BASE_DIR, "reference_files", "reference.docx")

# Ensure output folder exists
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

# Configuration for chunking
CHUNK_SIZE_WORDS = 1500
CHUNK_OVERLAP_WORDS = 150

# Active model for summarization (e.g., "gemini", "ollama")
ACTIVE_MODEL = "GEMINI"

# Embedding model for FAISS (using Universal Sentence Encoder)
# EMBEDDING_MODEL is no longer directly used as we are loading the model via tensorflow_hub

# Gemini configuration
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")

# Grok configuration
GROK_API_KEY = os.getenv("GROK_API_KEY", "") # Replace with actual Grok API key
GROK_MODEL = os.getenv("GROK_MODEL", "llama-3.1-8b-instant") # Replace with actual Grok model name

# OpenAI configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "") # Replace with actual OpenAI API key
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5-nano") # Replace with actual OpenAI model name


# Token limits for summarization
CORE_IDEAS_MAX_TOKENS = 4000
MASTER_SUMMARY_MAX_TOKENS = 4000
REWRITE_MAX_TOKENS = 10000
