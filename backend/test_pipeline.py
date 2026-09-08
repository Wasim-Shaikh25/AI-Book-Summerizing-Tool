"""Simple test to verify pipeline works after restructuring."""

import os
import sys
from pathlib import Path

# Set up environment
backend_root = Path(__file__).resolve().parent
project_root = backend_root.parent
os.environ["PROJECT_ROOT"] = str(project_root)
os.environ["PIPELINE_PDF"] = str(backend_root / "src/modules/debug/pdf_files/The Constitution Of India By Jhavala.pdf")
os.environ["REWRITE_USER_INSTRUCTION"] = "short easy notes, do not add extra details"
os.environ["PIPELINE_MAX_PAGES"] = "5"  # Test with only 5 pages
os.environ["FULL_REWRITE_MAX_CHUNKS"] = "3"  # Test with only 3 sections
os.environ["INGESTION_PROFILE"] = "fast_local"  # Use fast profile for testing
os.environ["USE_LLM_INTENT"] = "0"  # Skip intent routing for testing
os.environ["EXPORT_DOCX"] = "0"  # Skip DOCX export for faster testing

sys.path.insert(0, str(backend_root))

# Import and run pipeline check
from src.modules.pipeline import run_pipeline
from src.modules.ingestion.pdf_extractor import extract_pdf

print("=" * 60)
print("PIPELINE TEST - After Restructuring")
print("=" * 60)

pdf_path = os.environ["PIPELINE_PDF"]
print(f"PDF: {pdf_path}")
print(f"Max pages: {os.environ.get('PIPELINE_MAX_PAGES')}")
print(f"Max sections: {os.environ.get('FULL_REWRITE_MAX_CHUNKS')}")
print(f"Profile: {os.environ.get('INGESTION_PROFILE')}")

if not Path(pdf_path).exists():
    print(f"[!] PDF not found: {pdf_path}")
    sys.exit(1)

print("\n[1/2] Testing PDF extraction...")
try:
    lines, _, _ = extract_pdf(pdf_path, max_pages=5)
    print(f"      Extracted {len(lines)} lines from first 5 pages")
    if len(lines) > 0:
        # NormalizedLine objects have a 'text' attribute
        sample_text = lines[0].text if hasattr(lines[0], 'text') else str(lines[0])
        print(f"      Sample line: {sample_text[:100]}...")
except Exception as e:
    print(f"[!] PDF extraction failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n[2/2] Testing pipeline structure...")
try:
    result, logger = run_pipeline(pdf_path, enable_logs=True, persist_to_db=False)
    print(f"      Pipeline completed successfully")
    print(f"      Generated {len(list(result.lines))} lines")
    if logger:
        print(f"      Log directory: {logger.run_dir}")
except Exception as e:
    print(f"[!] Pipeline failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "=" * 60)
print("✅ Pipeline test PASSED")
print("=" * 60)
print("\nThe pipeline is properly wired after restructuring.")
print("To run full pipeline with rewrite:")
print(f"  PIPELINE_PDF=\"{pdf_path}\" REWRITE_USER_INSTRUCTION=\"short notes\" python scripts/run_full_openai_pipeline.py")
