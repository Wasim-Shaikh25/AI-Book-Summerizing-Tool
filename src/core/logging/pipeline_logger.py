from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


def _utc_timestamp_for_path() -> str:
    # Deterministic-ish per run, readable, filesystem-safe.
    return datetime.utcnow().strftime("%Y_%m_%d_%H_%M_%S")


def _json_dumps(payload: Any) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False)


def _read_json_if_exists(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


@dataclass(frozen=True, slots=True)
class PipelineLogger:
    """
    Per-run logger that writes deterministic JSON artifacts under:
      logs/run_<timestamp>/

    Supports:
      - write_json(name, payload): overwrite deterministic file
      - append_json_list(name, item): keep file as JSON list and append deterministically
    """

    run_dir: Path

    @staticmethod
    def create(*, base_dir: str = "logs") -> "PipelineLogger":
        base = Path(base_dir)
        base.mkdir(parents=True, exist_ok=True)
        run_dir = base / f"run_{_utc_timestamp_for_path()}"
        run_dir.mkdir(parents=True, exist_ok=True)
        return PipelineLogger(run_dir=run_dir)

    def path(self, filename: str) -> Path:
        return self.run_dir / filename

    def write_json(self, filename: str, payload: Any) -> None:
        # Safety: ensure run_dir exists (debug runners may create PipelineLogger then crash before folders exist)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.path(filename).write_text(_json_dumps(payload), encoding="utf-8")

    def append_json_list(self, filename: str, item: Any) -> None:
        # Safety: ensure run_dir exists
        self.run_dir.mkdir(parents=True, exist_ok=True)
        path = self.path(filename)
        existing = _read_json_if_exists(path)
        if existing is None:
            arr: List[Any] = []
        elif isinstance(existing, list):
            arr = existing
        else:
            # If an old non-list file exists, preserve it by wrapping.
            arr = [existing]
        arr.append(item)
        path.write_text(_json_dumps(arr), encoding="utf-8")

    def append_decision(
        self,
        heading_id: str,
        *,
        stage: str,
        decision: str,
        meta: Optional[Dict[str, Any]] = None,
        filename: str = "decision_trace.json",
    ) -> None:
        """
        Appends a decision event to decision_trace.json.

        Format:
        [
          {
            "heading_id": "L57",
            "history": [
              {"stage": "...", "decision": "...", "meta": {...}}
            ]
          }
        ]
        """
        path = self.path(filename)
        existing = _read_json_if_exists(path)
        if existing is None:
            data: List[Dict[str, Any]] = []
        elif isinstance(existing, list):
            data = existing  # type: ignore[assignment]
        else:
            data = []

        # Find or create entry
        entry: Optional[Dict[str, Any]] = None
        for item in data:
            if isinstance(item, dict) and item.get("heading_id") == heading_id:
                entry = item
                break
        if entry is None:
            entry = {"heading_id": heading_id, "history": []}
            data.append(entry)

        hist = entry.get("history")
        if not isinstance(hist, list):
            hist = []
            entry["history"] = hist

        event: Dict[str, Any] = {"stage": stage, "decision": decision}
        if meta:
            event["meta"] = meta
        hist.append(event)

        path.write_text(_json_dumps(data), encoding="utf-8")
