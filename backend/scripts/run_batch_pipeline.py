"""Run full pipeline + deterministic quality audit for multiple PDFs."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = Path(os.environ.get("PROJECT_ROOT", str(BACKEND_ROOT.parent)))
sys.path.insert(0, str(BACKEND_ROOT))
load_dotenv(PROJECT_ROOT / ".env")

DEFAULT_PDFS = [
    r"C:\Users\Shaikh Wasim\Downloads\family-law-43811769208.pdf",
    r"C:\Users\Shaikh Wasim\Downloads\constitutional-law-i-sem-ii-2022-23-1--43527772408.pdf",
    r"C:\Users\Shaikh Wasim\Downloads\environmental-law-1--43748672008.pdf",
    r"C:\Users\Shaikh Wasim\Downloads\bareact-140.pdf",
]

DEFAULT_REWRITE_INSTRUCTION = (
    "Create complete study notes in plain, simple English — easy to understand, not artificially short. "
    "Cover every important point from the source. Use prose paragraphs for explanations; "
    "use bullet lists only for examples or enumerations."
)


def _latest_log_dir(project_root: Path) -> Path | None:
    logs = project_root / "logs"
    if not logs.is_dir():
        return None
    runs = sorted(logs.glob("run_*"), key=lambda p: p.stat().st_mtime, reverse=True)
    return runs[0] if runs else None


def main() -> int:
    pdfs = [p.strip() for p in os.environ.get("BATCH_PIPELINE_PDFS", "").split("|") if p.strip()]
    if not pdfs:
        pdfs = DEFAULT_PDFS

    out_dir = PROJECT_ROOT / "output" / "batch"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y-%m-%d_%H-%M-%S")
    summary_path = out_dir / f"batch_run_{ts}.json"

    env = os.environ.copy()
    env["SKIP_STRUCTURE"] = "0"
    env["PIPELINE_LOG_DIR"] = ""
    env.setdefault("NOTES_QUALITY_AUDIT", "1")
    env.setdefault("NOTES_QUALITY_LLM", "1")
    env.setdefault("NOTES_QUALITY_LINE_AUDIT", "1")
    env.setdefault("USE_LLM_INTENT", "1")
    env.setdefault("NOTES_EXPORT_STYLE", "book")
    env.setdefault("EXPORT_DOCX", "1")
    env.setdefault("PIPELINE_MAX_PAGES", "0")
    env.setdefault(
        "REWRITE_USER_INSTRUCTION",
        os.environ.get("REWRITE_USER_INSTRUCTION", DEFAULT_REWRITE_INSTRUCTION),
    )
    env["PYTHONIOENCODING"] = "utf-8"

    results: list[dict] = []
    pipeline_script = BACKEND_ROOT / "scripts" / "run_full_openai_pipeline.py"

    for i, pdf in enumerate(pdfs, start=1):
        pdf_path = Path(pdf)
        label = pdf_path.stem
        print("=" * 72, flush=True)
        print(f"[{i}/{len(pdfs)}] {label}", flush=True)
        print(f"  PDF: {pdf_path}", flush=True)

        if not pdf_path.exists():
            print(f"  [!] Missing PDF — skipped", flush=True)
            results.append({"label": label, "pdf": str(pdf_path), "status": "missing_pdf"})
            continue

        book_env = env.copy()
        book_env["PIPELINE_PDF"] = str(pdf_path)

        proc = subprocess.run(
            [sys.executable, str(pipeline_script)],
            cwd=str(BACKEND_ROOT),
            env=book_env,
            capture_output=False,
            text=True,
        )
        if proc.returncode != 0:
            results.append({"label": label, "pdf": str(pdf_path), "status": "pipeline_failed"})
            print(f"  [!] Pipeline failed (exit {proc.returncode})", flush=True)
            continue

        md_files = sorted(
            (PROJECT_ROOT / "output").glob(f"{label}*.md"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        latest_md = md_files[0] if md_files else None
        report_txt = latest_md.with_suffix(".quality_report.txt") if latest_md else None
        report_json = latest_md.with_suffix(".quality_report.json") if latest_md else None
        log_dir = _latest_log_dir(PROJECT_ROOT)
        docx_files = sorted(
            (PROJECT_ROOT / "output").glob(f"{label}*.docx"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        latest_docx = docx_files[0] if docx_files else None

        verdict = ""
        coverage_pct = ""
        if report_json and report_json.exists():
            payload = json.loads(report_json.read_text(encoding="utf-8"))
            summary = payload.get("summary") or {}
            verdict = str(summary.get("verdict") or summary.get("overall") or "")
            coverage_pct = str(summary.get("coverage_pct") or "")

        results.append(
            {
                "label": label,
                "pdf": str(pdf_path),
                "status": "ok",
                "md": str(latest_md) if latest_md else "",
                "docx": str(latest_docx) if latest_docx else "",
                "log_dir": str(log_dir) if log_dir else "",
                "quality_report": str(report_txt) if report_txt and report_txt.exists() else "",
                "quality_json": str(report_json) if report_json and report_json.exists() else "",
                "verdict": verdict,
                "coverage_pct": coverage_pct,
            }
        )
        print(f"  [+] Verdict: {verdict or 'n/a'} | coverage: {coverage_pct or 'n/a'}%", flush=True)
        if report_txt and report_txt.exists():
            print(f"  [+] Report: {report_txt}", flush=True)

    summary_path.write_text(json.dumps({"books": results, "generated_at": ts}, indent=2), encoding="utf-8")
    print("=" * 72, flush=True)
    print(f"[+] Batch summary: {summary_path}", flush=True)

    ok_books = [r for r in results if r.get("status") == "ok" and r.get("md") and r.get("log_dir")]
    if ok_books:
        manifest_path = out_dir / f"batch_manifest_{ts}.json"
        manifest_books = [
            {
                "label": r["label"],
                "pdf": r["pdf"],
                "log_dir": r["log_dir"],
                "md": r["md"],
                "docx": r.get("docx") or "",
            }
            for r in ok_books
        ]
        manifest_path.write_text(json.dumps({"books": manifest_books}, indent=2), encoding="utf-8")
        combined_md = out_dir / f"batch_side_by_side_{ts}.md"
        combined_json = out_dir / f"batch_side_by_side_{ts}.json"
        try:
            from src.modules.quality.analyzer import run_batch_audit

            run_batch_audit(
                manifest_path,
                audit_dir=PROJECT_ROOT / "output" / "audit",
                combined_out=combined_md,
                json_out=combined_json,
            )
            print(f"[+] Side-by-side audit: {combined_md}", flush=True)
        except Exception as exc:
            print(f"[!] Combined audit failed: {exc}", flush=True)

    print("\n## Side-by-side summary", flush=True)
    print(
        "| Book | Verdict | Coverage % | Heading AC | Completeness |",
        flush=True,
    )
    print("|------|---------|------------|------------|--------------|", flush=True)
    for r in results:
        if r.get("status") != "ok":
            print(f"| {r.get('label', '?')} | **{r.get('status')}** | — | — | — |", flush=True)
            continue
        scores: dict = {}
        heading_ac = "n/a"
        if r.get("quality_json"):
            try:
                payload = json.loads(Path(r["quality_json"]).read_text(encoding="utf-8"))
                summary = payload.get("summary") or {}
                scores = summary.get("scores") or {}
                heading_ac = str(summary.get("heading_acceptance") or "n/a")
            except Exception:
                pass
        print(
            f"| {r.get('label', '?')} | {r.get('verdict') or 'n/a'} | "
            f"{r.get('coverage_pct') or 'n/a'} | {heading_ac} | "
            f"{scores.get('completeness', 'n/a')} |",
            flush=True,
        )

    failed = [r for r in results if r.get("status") != "ok"]
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
