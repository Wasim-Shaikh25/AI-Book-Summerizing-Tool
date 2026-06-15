"""End-to-end scenario tests for rewrite + Q&A flows."""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path(os.environ.get('PROJECT_ROOT', str(BACKEND_ROOT.parent)))
sys.path.insert(0, str(BACKEND_ROOT))
load_dotenv(PROJECT_ROOT / ".env")

from src import config
from src.modules.pipeline.stage_registry import STAGE_15D, STAGE_15E, STAGE_15F, resolve_existing_artifact
from src.modules.generation.qa_engine import retrieve_sections
from src.modules.generation.rewrite import RewriteEngine
from src.modules.generation.qa_engine import BookQaEngine
from src.modules.generation.toc_sections import load_chapter_hierarchy_json, load_rewrite_sections
from src.modules.ingestion.pdf_extractor import extract_pdf
from src.modules.interaction.command_parser import CommandParser
from src.modules.storage.knowledge_store import KnowledgeStore

PDF = os.environ.get(
    "PIPELINE_PDF",
    r"C:\Users\Shaikh Wasim\Downloads\LAW OF TORTS, MOTOR ACCIDENT CLAIMS AND CONSUMER (1).pdf",
)
LOG_DIR = Path(
    os.environ.get(
        "PIPELINE_LOG_DIR",
        str(PROJECT_ROOT / "logs" / "run_2026-05-31_10-10-14"),
    )
)
OUT = PROJECT_ROOT / "output" / "e2e_scenarios"
MAX_SECTIONS = int(os.environ.get("E2E_MAX_SECTIONS", "6") or "6")


def _book_context():
    store = KnowledgeStore()
    row = store.get_connection().execute(
        "SELECT book_id, title FROM books ORDER BY processed_at DESC LIMIT 1"
    ).fetchone()
    if not row:
        raise RuntimeError("No book in DB — run structure pipeline first.")
    book_id, title = row[0], row[1]
    lines, _, _ = extract_pdf(PDF)
    hierarchy_path = resolve_existing_artifact(LOG_DIR, STAGE_15F) or resolve_existing_artifact(
        LOG_DIR, STAGE_15E
    )
    sections = load_rewrite_sections(
        store,
        book_id=book_id,
        pdf_path=PDF,
        ultimate_sections_path=resolve_existing_artifact(LOG_DIR, STAGE_15D),
        chapter_hierarchy_path=hierarchy_path,
        lines=lines,
        prefer_15e=True,
        prefer_15d=True,
    )
    hierarchy = load_chapter_hierarchy_json(hierarchy_path) if hierarchy_path else {}
    return store, book_id, title, sections, hierarchy, hierarchy_path


def _analyze_rewrite(md: str, instruction: str) -> dict:
    low = md.lower()
    has_key = "### key points" in low
    has_quick = "### quick revision" in low
    has_mermaid = "```mermaid" in low
    bullets = len(re.findall(r"^\s*[-*]\s+", md, re.MULTILINE))
    return {
        "chars": len(md),
        "has_key_points": has_key,
        "has_quick_revision": has_quick,
        "has_mermaid": has_mermaid,
        "bullet_count": bullets,
        "instruction": instruction[:80],
    }


def _run_rewrite(
    engine: RewriteEngine,
    *,
    instruction: str,
    exam_oriented: bool,
    compact: bool,
    label: str,
) -> dict:
    os.environ["EXAM_ORIENTED"] = "1" if exam_oriented else "0"
    os.environ["COMPACT_EXAM"] = "1" if compact else "0"
    hierarchy_path = resolve_existing_artifact(LOG_DIR, STAGE_15F) or resolve_existing_artifact(
        LOG_DIR, STAGE_15E
    )
    lines, _, _ = extract_pdf(PDF)
    result = engine.run(
        user_instruction=instruction,
        export_to_word=False,
        max_sections=MAX_SECTIONS,
        pdf_path=PDF,
        ultimate_sections_path=resolve_existing_artifact(LOG_DIR, STAGE_15D),
        chapter_hierarchy_path=hierarchy_path,
        lines=lines,
    )
    if "error" in result:
        return {"label": label, "ok": False, "error": result["error"]}
    md = result.get("markdown") or ""
    analysis = _analyze_rewrite(md, instruction)
    path = OUT / f"{label}.md"
    path.write_text(md, encoding="utf-8")
    analysis.update({"label": label, "ok": True, "path": str(path), "sections": result.get("section_count")})
    return analysis


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    report: dict = {"timestamp": datetime.utcnow().isoformat(), "max_sections": MAX_SECTIONS, "scenarios": []}

    print("=" * 70)
    print("E2E SCENARIO TESTS")
    print(f"  PDF: {PDF}")
    print(f"  Log dir: {LOG_DIR}")
    print(f"  Sections per rewrite: {MAX_SECTIONS}")
    print("=" * 70)

    store, book_id, title, sections, hierarchy, _ = _book_context()
    engine = RewriteEngine(store, book_id=book_id, book_title=title)

    if getattr(config, "RAG_ENABLED", True):
        try:
            from src.modules.rag.service import RagService

            idx = RagService(store).ensure_index(book_id=book_id, sections=sections)
            print(f"RAG index: {idx.chunk_count} chunks for book_id={book_id}")
        except Exception as exc:
            print(f"RAG index skipped: {exc}")

    # Scenario 1
    print("\n[1/5] Rewrite full PDF in simple English...")
    s1 = _run_rewrite(
        engine,
        instruction="rewrite the full book in simple English, easy to read, no extra details",
        exam_oriented=False,
        compact=False,
        label="scenario1_simple_english",
    )
    s1["expect"] = "simple prose, no forced exam blocks"
    s1["pass"] = s1.get("ok") and not s1.get("has_quick_revision", True)
    report["scenarios"].append(s1)
    print(f"  -> {'PASS' if s1['pass'] else 'FAIL'} bullets={s1.get('bullet_count')} chars={s1.get('chars')}")

    # Scenario 2
    print("\n[2/5] Exam prep — very simple English, short...")
    s2 = _run_rewrite(
        engine,
        instruction="rewrite for exam preparation in very simple English, short explanations only",
        exam_oriented=True,
        compact=False,
        label="scenario2_exam_prep",
    )
    s2["expect"] = "Key Points + Quick Revision blocks"
    s2["pass"] = s2.get("ok") and s2.get("has_key_points") and s2.get("has_quick_revision")
    report["scenarios"].append(s2)
    print(f"  -> {'PASS' if s2['pass'] else 'FAIL'} key={s2.get('has_key_points')} quick={s2.get('has_quick_revision')}")

    # Scenario 3
    print("\n[3/5] Ultra-short notes with diagrams if helpful...")
    s3 = _run_rewrite(
        engine,
        instruction=(
            "create very short notes in very simple English for quick exam preparation; "
            "explain only important concepts; add mermaid diagram if it helps understanding"
        ),
        exam_oriented=True,
        compact=True,
        label="scenario3_ultra_short",
    )
    s3["expect"] = "compact Key Points only, optional mermaid"
    s3["pass"] = s3.get("ok") and s3.get("has_key_points") and not s3.get("has_quick_revision")
    report["scenarios"].append(s3)
    print(f"  -> {'PASS' if s3['pass'] else 'FAIL'} compact bullets={s3.get('bullet_count')}")

    # Scenario 4 — three topic Q&A
    print("\n[4/5] Explain 3 topics from the book...")
    qa = BookQaEngine(book_title=title, subject_hint="Law of Torts", book_id=book_id)
    topics = [
        "Explain the definition of tort in simple English",
        "Explain damnum sine injuria and injuria sine damno with examples",
        "Explain negligence and breach of duty for exam preparation",
    ]
    s4_results = []
    for i, q in enumerate(topics, start=1):
        ans = qa.answer(q, sections, allow_external=True, depth="short", language_level="simple")
        text = ans.get("answer") or ""
        ok = len(text) > 80 and not text.startswith("[!]")
        path = OUT / f"scenario4_topic{i}.md"
        path.write_text(f"# Question\n{q}\n\n# Answer\n{text}\n\nSources: {ans.get('sources')}\n", encoding="utf-8")
        s4_results.append({"question": q, "ok": ok, "chars": len(text), "sources": ans.get("sources"), "path": str(path)})
        print(f"  Topic {i}: {'PASS' if ok else 'FAIL'} ({len(text)} chars)")
    s4 = {"label": "scenario4_topic_qa", "pass": all(r["ok"] for r in s4_results), "topics": s4_results}
    report["scenarios"].append(s4)

    # Scenario 5 — scenario question in-domain vs out-of-domain
    print("\n[5/5] Scenario questions (in-domain vs unrelated)...")
    in_q = (
        "Scenario: A delivery driver is texting while driving and hits a pedestrian at a crossing. "
        "The pedestrian suffers a leg fracture. Analyze potential tort liability under negligence principles."
    )
    out_q = "Explain how chlorophyll captures light energy during photosynthesis in plant cells."

    in_ans = qa.answer(in_q, sections, allow_external=True, depth="medium", language_level="simple")
    out_ans = qa.answer(out_q, sections, allow_external=True, depth="medium", language_level="simple")

    in_text = in_ans.get("answer") or ""
    out_text = out_ans.get("answer") or ""
    in_ok = len(in_text) > 100 and any(w in in_text.lower() for w in ("negligence", "duty", "liability", "damages"))
    out_ok = (not out_ans.get("related", True)) or any(
        w in out_text.lower() for w in ("not related", "outside", "cannot", "tort", "law of torts")
    ) and "chlorophyll" not in out_text.lower()[:200]

    (OUT / "scenario5_in_domain.md").write_text(in_text, encoding="utf-8")
    (OUT / "scenario5_out_domain.md").write_text(out_text, encoding="utf-8")

    s5 = {
        "label": "scenario5_scenario_guard",
        "pass": in_ok and out_ok,
        "in_domain": {"related": in_ans.get("related"), "ok": in_ok, "preview": in_text[:200]},
        "out_domain": {"related": out_ans.get("related"), "ok": out_ok, "preview": out_text[:200]},
    }
    report["scenarios"].append(s5)
    print(f"  In-domain tort scenario: {'PASS' if in_ok else 'FAIL'}")
    print(f"  Out-of-domain biology: {'PASS' if out_ok else 'FAIL'} (related={out_ans.get('related')})")

    # Parser smoke
    parser = CommandParser()
    p1 = parser.parse_intent("rewrite the book in simple English")
    p2 = parser.parse_intent("explain volenti non fit injuria")
    report["parser"] = {
        "rewrite_simple": p1.model_dump() if hasattr(p1, "model_dump") else str(p1),
        "explain_intent": p2.model_dump() if hasattr(p2, "model_dump") else str(p2),
    }

    report_path = OUT / "e2e_report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    passed = sum(1 for s in report["scenarios"] if s.get("pass"))
    total = len(report["scenarios"])
    print("\n" + "=" * 70)
    print(f"SUMMARY: {passed}/{total} scenarios passed")
    print(f"Report: {report_path}")
    print("=" * 70)
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
