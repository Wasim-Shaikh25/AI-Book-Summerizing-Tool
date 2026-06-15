#!/usr/bin/env python3
"""Run fast_local structure pipeline + sample rewrite + print summary paths."""

from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

BACKEND = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get("PROJECT_ROOT", str(BACKEND.parent)))
sys.path.insert(0, str(BACKEND))
load_dotenv(ROOT / ".env")

PDF = os.environ.get(
    "PIPELINE_PDF",
    str(
        ROOT
        / "output/uploads/626ec4a3-7144-4170-bd23-3c1deb60ceb6/LAW OF TORTS, MOTOR ACCIDENT CLAIMS AND CONSUMER (1).pdf"
    ),
)


def main() -> int:
    from src.modules.ingestion.profile import ingestion_profile_context
    from src.modules.pipeline import run_pipeline
    from src.modules.pipeline.stage_registry import (
        STAGE_15D,
        STAGE_15E,
        STAGE_15F,
        resolve_existing_artifact,
    )

    pdf = Path(PDF)
    if not pdf.exists():
        print(f"[!] PDF not found: {pdf}")
        return 1

    max_pages = int(os.environ.get("PIPELINE_MAX_PAGES", "0") or "0")
    profile = os.environ.get("INGESTION_PROFILE", "fast_local")

    print("=" * 60)
    print("UPGRADE VALIDATION — structure pipeline")
    print(f"  PDF:     {pdf}")
    print(f"  profile: {profile}")
    print(f"  pages:   {'all' if max_pages <= 0 else max_pages}")
    print("=" * 60)

    def on_progress(stage_id: str, message: str, percent: int) -> None:
        print(f"  [{percent:3d}%] {stage_id}: {message}")

    with ingestion_profile_context(profile):
        if max_pages > 0:
            os.environ["PIPELINE_MAX_PAGES"] = str(max_pages)
        result, logger = run_pipeline(
            str(pdf),
            enable_logs=True,
            persist_to_db=False,
            on_progress=on_progress,
        )

    if not logger:
        print("[!] No logger — enable_logs failed")
        return 1

    log_dir = logger.run_dir
    print(f"\n[OK] Structure complete")
    print(f"  log_dir: {log_dir}")
    print(f"  headings: {len(result.final_headings)}")
    print(f"  fragments: {len(result.fragments)}")
    print(f"  pages: {result.total_pages}")

    for key, label in [
        (STAGE_15D, "15d sections"),
        (STAGE_15E, "15e chapters"),
        (STAGE_15F, "15f cleanup"),
    ]:
        path = resolve_existing_artifact(log_dir, key)
        if path and path.exists():
            import json

            data = json.loads(path.read_text(encoding="utf-8"))
            if key == STAGE_15D:
                n = len(data.get("sections") or [])
                meta = data.get("meta") or {}
                print(f"  {label}: {n} sections, folds={meta.get('semantic_low_coherence_folds', 0)}")
            elif key == STAGE_15E:
                n = len(data.get("chapters") or [])
                meta = data.get("meta") or {}
                print(f"  {label}: {n} chapters, method={meta.get('assignment_method')}")
            else:
                meta = data.get("meta") or {}
                print(f"  {label}: method={meta.get('heading_cleanup_method')}, weak_after={meta.get('weak_section_headings_after')}")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    env_file = ROOT / "output" / f"last_validation_run_{stamp}.env"
    env_file.write_text(
        f"PIPELINE_LOG_DIR={log_dir.as_posix()}\nPIPELINE_PDF={pdf.as_posix()}\n",
        encoding="utf-8",
    )
    print(f"\nSaved run info: {env_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
