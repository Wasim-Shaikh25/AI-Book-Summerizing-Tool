import json

# Load extracted headings
with open('c:/python_project/AI Notes Creater Model/logs/run_2026-07-09_12-39-34/s07_final_headings.json', encoding='utf-8') as f:
    extracted_data = json.load(f)

# Check if it's a dict or list
if isinstance(extracted_data, dict):
    extracted_headings = extracted_data.get('items', [])
else:
    extracted_headings = extracted_data

print(f"Total headings extracted from PDF: {len(extracted_headings)}")
print("\nSample extracted headings:")
for i, h in enumerate(extracted_headings[:20]):
    text = h.get('text', '')[:80] if isinstance(h, dict) else str(h)[:80]
    level = h.get('level', 'N/A') if isinstance(h, dict) else 'N/A'
    print(f"  {i+1}. [{level}] {text}")

# Load sections used in pipeline
with open('c:/python_project/AI Notes Creater Model/logs/run_2026-07-09_12-39-34/s15d_ultimate_sections.json', encoding='utf-8') as f:
    sections_data = json.load(f)

# Check structure
if isinstance(sections_data, dict):
    items = sections_data.get('items', {})
    sections = items.get('sections', []) if isinstance(items, dict) else []
else:
    sections = sections_data

section_headings = [s.get('heading', '') for s in sections if isinstance(s, dict)]
print(f"\nSections used for rewrite: {len(section_headings)}")
print("\nSection headings used:")
for i, h in enumerate(section_headings[:20]):
    print(f"  {i+1}. {h[:80]}")

# Load chapter hierarchy
with open('c:/python_project/AI Notes Creater Model/logs/run_2026-07-09_12-39-34/s15e_chapter_hierarchy.json', encoding='utf-8') as f:
    hierarchy_data = json.load(f)

# Check structure
if isinstance(hierarchy_data, dict):
    chapters = hierarchy_data.get('items', [])
else:
    chapters = hierarchy_data

print(f"\nChapters detected: {len(chapters)}")
if isinstance(chapters, list):
    for ch in chapters[:5]:
        if isinstance(ch, dict):
            print(f"  Chapter: {ch.get('chapter_title', '')[:60]}")
            for sec in ch.get('sections', [])[:3]:
                if isinstance(sec, dict):
                    print(f"    Section: {sec.get('heading', '')[:60]}")
