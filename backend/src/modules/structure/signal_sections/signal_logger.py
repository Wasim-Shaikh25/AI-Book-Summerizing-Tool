"""Signal-Sections logger — write artifacts to a dedicated ``logs/run_signal_<ts>/`` tree.

Isolated from the existing pipeline logger so the existing audit / re-export
scripts that scan ``logs/run_<ts>/`` never see these artifacts.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional


_SIGNAL_LOG_PREFIX = "run_signal_"


def _logs_root() -> Path:
    """Resolve ``LOGS_FOLDER`` (same constant the rest of the project uses)."""
    from src.shared.config import LOGS_FOLDER  # imported lazily to avoid cycles

    p = Path(LOGS_FOLDER)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _utc_stamp() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d_%H-%M-%S")


def resolve_signal_log_dir(*, explicit: Optional[str] = None) -> Path:
    """Create + return the directory where signal artifacts will be written.

    If ``explicit`` is provided, use it (relative paths resolve under
    ``LOGS_FOLDER``). Otherwise create ``logs/run_signal_<utc>/``.
    """
    if explicit:
        p = Path(explicit)
        if not p.is_absolute():
            p = _logs_root() / explicit
        p.mkdir(parents=True, exist_ok=True)
        return p
    p = _logs_root() / f"{_SIGNAL_LOG_PREFIX}{_utc_stamp()}"
    p.mkdir(parents=True, exist_ok=True)
    return p


class SignalRunLogger:
    """Thin JSON artifact writer for the signal-sections pipeline."""

    # Artifact filenames (kept stable so re-runs/tests can find them).
    BOUNDARIES = "signal_boundaries.json"
    HIERARCHY = "signal_hierarchy.json"
    REWRITTEN = "signal_rewritten.json"
    RUN_META = "signal_run_meta.json"

    def __init__(self, run_dir: Path) -> None:
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.run_id = self.run_dir.name

    def write_json(self, filename: str, payload: Any) -> Path:
        path = self.run_dir / filename
        text = json.dumps(payload, indent=2, ensure_ascii=False, default=str)
        path.write_text(text, encoding="utf-8")
        return path

    def write_boundaries(self, payload: Any) -> Path:
        return self.write_json(self.BOUNDARIES, payload)

    def write_hierarchy(self, payload: Any) -> Path:
        return self.write_json(self.HIERARCHY, payload)

    def write_rewritten(self, payload: Any) -> Path:
        return self.write_json(self.REWRITTEN, payload)

    def write_run_meta(self, payload: Dict[str, Any]) -> Path:
        meta = dict(payload)
        meta.setdefault("run_id", self.run_id)
        meta.setdefault("run_dir", str(self.run_dir))
        meta.setdefault("finished_at", datetime.utcnow().isoformat(timespec="seconds") + "Z")
        return self.write_json(self.RUN_META, meta)
