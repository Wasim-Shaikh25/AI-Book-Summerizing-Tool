import sys
from pathlib import Path

# Ensure repo root is on sys.path when running as: python scripts/inspect_pdf_output.py
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

# Adjust import if needed
from src.utils import pdf_reader

PDF_PATH = Path("reference_files/law_of_tort.pdf")

if not PDF_PATH.exists():
    print("PDF not found:", PDF_PATH)
    sys.exit(1)

# Try common extraction patterns
if hasattr(pdf_reader, "extract_text"):
    text = pdf_reader.extract_text(str(PDF_PATH))
elif hasattr(pdf_reader, "read_pdf"):
    text = pdf_reader.read_pdf(str(PDF_PATH))
elif hasattr(pdf_reader, "PDFReader"):
    reader = pdf_reader.PDFReader(pdf_folder=str(PDF_PATH.parent))
    text = reader.read_all_pdfs(specific_file=str(PDF_PATH))
else:
    raise RuntimeError("No known PDF extraction function found in pdf_reader.py")

print("\n========== PDF EXTRACTION DIAGNOSTIC ==========\n")
print("Return type:", type(text))
print("Is str:", isinstance(text, str))
print("Is list:", isinstance(text, list))
print("Is dict:", isinstance(text, dict))

def print_first_50_lines(s: str) -> None:
    print("\n----- FIRST 50 LINES -----\n")
    lines = (s or "").split("\n")
    for i, line in enumerate(lines[:50]):
        print(f"{i:02d} | {repr(line)}")

if isinstance(text, str):
    print("Length:", len(text))
    print("Total newline count:", text.count("\n"))
    print_first_50_lines(text)

elif isinstance(text, list):
    print("List length:", len(text))
    if len(text) > 0:
        print("First item type:", type(text[0]))
    if len(text) > 1:
        print("Second item type:", type(text[1]))

    if len(text) > 0 and isinstance(text[0], str):
        print("First item length:", len(text[0]))
        print("Newlines in first item:", text[0].count("\n"))
        print("\n----- FIRST 50 LINES OF FIRST ITEM -----\n")
        lines = text[0].split("\n")
        for i, line in enumerate(lines[:50]):
            print(f"{i:02d} | {repr(line)}")

    elif len(text) > 0:
        print("\nFirst item repr:", repr(text[0]))

else:
    print("Unhandled return type structure.")
    print("Repr:", repr(text))
