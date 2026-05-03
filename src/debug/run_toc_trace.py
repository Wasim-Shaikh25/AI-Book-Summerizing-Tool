"""
Debug runner: end-to-end TOC trace with deterministic pipeline artifacts.

Runs the same path as production (`run_pipeline` with logging + optional DB persist):
  layout → noise → candidates → heading gate → continuity → fragments → TOC pass-through
  → deterministic TOC / metadata → final headings JSON.

Flags:
  --visualize       Write visualization.pdf in the run folder.
  --open-folder     Open the run folder in the system file manager (Windows: Explorer).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

# Allow running as a script: `python src/debug/run_toc_trace.py`
# by ensuring project root is on sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def run(pdf_path: str) -> Path:
    """
    Thin debug wrapper around the production pipeline.

    Behavior:
      - Calls src.book_pipeline.run_pipeline(...) with logging ENABLED
      - Returns the created run folder path from the production logger
    """
    from src.book_pipeline import run_pipeline

    pdf_abs = str(Path(pdf_path).resolve())
    _, logger = run_pipeline(pdf_abs, enable_logs=True, persist_to_db=True)
    if logger is None:
        raise RuntimeError("Expected enable_logs=True to return a PipelineLogger")
    return logger.run_dir


def _write_latest_run_pointer(run_dir: Path) -> Path:
    """Single file under logs/ so IDE/Explorer can open the current run, not an old run_* folder."""
    root = Path(__file__).resolve().parents[2]
    marker = root / "logs" / "LATEST_RUN.txt"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(str(run_dir.resolve()) + "\n", encoding="utf-8")
    return marker


def _print_deterministic_toc_summary(run_dir: Path) -> None:
    """Runtime summary so this run is not confused with older logs/run_* folders."""
    p = run_dir / "10_deterministic_toc.json"
    if not p.exists():
        return
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        items = data.get("items") or []
        p1_seeds = sum(
            1
            for it in items
            if isinstance(it, dict)
            and it.get("kind") == "seed_heading"
            and it.get("page_number") == 1
        )
        n = int(data.get("total_items", len(items)))
        print(
            f"[i] Deterministic TOC: {p1_seeds} seed_heading(s) on page 1; "
            f"total_items in 10_deterministic_toc.json = {n}"
        )
        print(f"[i] Use artifacts only under this run folder (not older logs/run_*).")
    except Exception:
        pass


def _open_in_file_manager(run_dir: Path) -> None:
    try:
        if sys.platform == "win32":
            os.startfile(run_dir)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.run(["open", str(run_dir)], check=False)
        else:
            subprocess.run(["xdg-open", str(run_dir)], check=False)
        print(f"[+] Opened run folder in file manager:\n    {run_dir}")
    except Exception as e:
        print(f"[!] Could not open run folder: {e}")


if __name__ == "__main__":
    _FLAG = frozenset({"--visualize", "--open-folder"})
    visualize = "--visualize" in sys.argv
    open_folder = "--open-folder" in sys.argv
    pos = [a for a in sys.argv[1:] if a not in _FLAG]

    if len(pos) > 0:
        pdf = pos[0]
    else:
        pdf = os.getenv("PDF_PATH", "src/debug/pdf_files/input.pdf")

    out = Path(run(pdf)).resolve()
    ptr = _write_latest_run_pointer(out)
    print(f"[i] Open this file for the current run path:\n    {ptr.resolve()}")

    # Optional: create a color-marked PDF for quick visual inspection.
    # This is best-effort and should never break the trace run.
    if visualize:
        try:
            from src.debug.visualizer import visualize_run

            vis_path = visualize_run(pdf_path=pdf, run_dir=str(out))
            print(f"[+] Visualization PDF:\n    {Path(vis_path).resolve()}")
        except Exception as e:
            print(f"[!] Visualization failed: {e}")
            try:
                from src.debug.visualizer import visualize_run

                vis_path = visualize_run(pdf_path=pdf, run_dir=str(out.parent))
                print(f"[+] Visualization PDF (fallback):\n    {Path(vis_path).resolve()}")
            except Exception as e2:
                print(f"[!] Visualization retry failed: {e2}")

    print(f"[+] TOC trace folder (open this run only; ignore older logs/run_*):\n    {out}")
    _print_deterministic_toc_summary(out)

    if open_folder:
        _open_in_file_manager(out)
