from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from src import config
from src.modules.pipeline.stage_registry import ALLOWED_LOG_FILES, stage_log_filename


def _utc_timestamp_for_path() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d_%H-%M-%S")


def _json_dumps(payload: Any) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False)


@dataclass(frozen=True, slots=True)
class PipelineLogger:
    """
    Per-run logger that writes deterministic JSON artifacts under:
      {LOGS_FOLDER}/run_<timestamp>/  (PROJECT_ROOT/logs by default)

    Stage keys and filenames are defined in ``stage_registry.STAGE_LOG_FILES``.
    """

    run_dir: Path
    run_id: str
    pdf_file: str

    @staticmethod
    def create(
        *,
        pdf_file: str = "",
        base_dir: str | None = None,
        enabled: bool = True,
    ) -> "PipelineLogger":
        if base_dir is None:
            base_dir = str(getattr(config, "LOGS_FOLDER", "logs"))
        if not enabled:
            return NoOpPipelineLogger(run_dir=Path(base_dir), run_id="", pdf_file=pdf_file)

        base = Path(base_dir)
        base.mkdir(parents=True, exist_ok=True)
        run_id = _utc_timestamp_for_path()
        run_dir = base / f"run_{run_id}"
        run_dir.mkdir(parents=True, exist_ok=True)
        return PipelineLogger(run_dir=run_dir, run_id=run_id, pdf_file=pdf_file)

    def path(self, filename: str) -> Path:
        return self.run_dir / filename

    def _assert_allowed(self, filename: str) -> None:
        if filename not in ALLOWED_LOG_FILES:
            raise ValueError(f"Refusing to write non-whitelisted log file: {filename}")

    def _envelope(self, stage_name: str, items: Any) -> Dict[str, Any]:
        if isinstance(items, dict):
            total_items = len(items)
        elif isinstance(items, list):
            total_items = len(items)
        else:
            total_items = 1
        return {
            "run_id": self.run_id,
            "stage": stage_name,
            "pdf_file": self.pdf_file,
            "timestamp": datetime.utcnow().isoformat(),
            "total_items": total_items,
            "items": items,
        }

    def write_stage(self, stage_name: str, items: List[Any]) -> None:
        filename = stage_log_filename(stage_name)
        self._assert_allowed(filename)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        payload = self._envelope(stage_name, items)
        self.path(filename).write_text(_json_dumps(payload), encoding="utf-8")

    def write_stage_payload(self, stage_name: str, payload: Any) -> None:
        """Write a stage log where ``items`` may be a dict (15c/15d/16) or list."""
        filename = stage_log_filename(stage_name)
        self._assert_allowed(filename)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        envelope = self._envelope(stage_name, payload)
        self.path(filename).write_text(_json_dumps(envelope), encoding="utf-8")


@dataclass(frozen=True, slots=True)
class NoOpPipelineLogger(PipelineLogger):
    """Drop-in replacement that writes nothing (production runs with logging disabled)."""

    def _assert_allowed(self, filename: str) -> None:
        return

    def path(self, filename: str) -> Path:
        return Path("")

    def write_stage(self, stage_name: str, items: List[Any]) -> None:
        return

    def write_stage_payload(self, stage_name: str, payload: Any) -> None:
        return
