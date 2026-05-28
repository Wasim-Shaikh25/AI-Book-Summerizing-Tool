from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


def _utc_timestamp_for_path() -> str:
    # Deterministic-ish per run, readable, filesystem-safe.
    # Spec expects: 2026-03-20_15-41-22
    return datetime.utcnow().strftime("%Y-%m-%d_%H-%M-%S")


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

    Contract:
      - Each stage log is a single JSON file with a common envelope.
      - Only allow writing the 10 whitelisted files for a run.
    """

    run_dir: Path
    run_id: str
    pdf_file: str

    _ALLOWED_FILES = {
        "01_layout_lines.json",
        "02_noise_filter.json",
        "03_candidate_scoring.json",
        "03b_heading_validity_gate.json",
        "04_llm_heading_validation.json",
        "04b_toc_candidate_gate.json",
        "05_llm_toc_classification.json",
        "06_toc_section_eval.json",
        "07_fragments.json",
        "08_hierarchy.json",
        "08b_continuity_filter.json",
        "09_final_headings.json",
        "10_deterministic_toc.json",
        "11_book_metadata.json",
        "12_final_headings_2.json",
        "13_visual_elements.json",
        "14_doubted_sections.json",
        "15a_heading_hierarchy.json",
        "15b_doubted_resolved.json",
        "15b_revalidation.json",
        "15c_final_book.json",
        "15d_ultimate_sections.json",
        "15e_chapter_hierarchy.json",
        "16_rag_snapshot.json",
        "decision_trace.json",
    }

    _STAGE_TO_FILE = {
        "layout_lines": "01_layout_lines.json",
        "noise_filter": "02_noise_filter.json",
        "candidate_scoring": "03_candidate_scoring.json",
        "heading_validity_gate": "03b_heading_validity_gate.json",
        "llm_heading_validation": "04_llm_heading_validation.json",
        "toc_candidate_gate": "04b_toc_candidate_gate.json",
        "llm_toc_classification": "05_llm_toc_classification.json",
        "toc_section_eval": "06_toc_section_eval.json",
        "fragments": "07_fragments.json",
        "hierarchy": "08_hierarchy.json",
        "continuity_filter": "08b_continuity_filter.json",
        "final_headings": "09_final_headings.json",
        "deterministic_toc": "10_deterministic_toc.json",
        "book_metadata": "11_book_metadata.json",
        "final_headings_2": "12_final_headings_2.json",
        "visual_elements": "13_visual_elements.json",
        "doubted_sections": "14_doubted_sections.json",
        "doubted_resolved": "15b_doubted_resolved.json",
        "revalidation": "15b_revalidation.json",
        "15a_heading_hierarchy": "15a_heading_hierarchy.json",
        "15c_final_book": "15c_final_book.json",
        "15d_ultimate_sections": "15d_ultimate_sections.json",
        "15e_chapter_hierarchy": "15e_chapter_hierarchy.json",
        "16_rag_snapshot": "16_rag_snapshot.json",
    }

    @staticmethod
    def create(*, pdf_file: str = "", base_dir: str = "logs", enabled: bool = True) -> "PipelineLogger":
        """
        If enabled is False, returns a NoOpPipelineLogger that performs no filesystem writes.
        """
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
        if filename not in self._ALLOWED_FILES:
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
        filename = self._STAGE_TO_FILE.get(stage_name)
        if not filename:
            raise ValueError(f"Unknown stage_name: {stage_name}")
        self._assert_allowed(filename)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        payload = self._envelope(stage_name, items)
        self.path(filename).write_text(_json_dumps(payload), encoding="utf-8")

    def write_stage_payload(self, stage_name: str, payload: Any) -> None:
        """Write a stage log where ``items`` may be a dict (15c/15d/16) or list."""
        filename = self._STAGE_TO_FILE.get(stage_name)
        if not filename:
            raise ValueError(f"Unknown stage_name: {stage_name}")
        self._assert_allowed(filename)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        envelope = self._envelope(stage_name, payload)
        self.path(filename).write_text(_json_dumps(envelope), encoding="utf-8")

    def record_decision(
        self,
        entity_id: str,
        stage: str,
        decision: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Appends a decision event to decision_trace.json.

        Output shape:
        [
          {
            "heading_id": "L245",
            "text": "...",   # optional if known by caller
            "history": [
              {"stage": "...", "decision": "...", ...metadata }
            ]
          }
        ]
        """
        filename = "decision_trace.json"
        self._assert_allowed(filename)

        path = self.path(filename)
        existing = _read_json_if_exists(path)
        if existing is None:
            data: List[Dict[str, Any]] = []
        elif isinstance(existing, list):
            data = existing  # type: ignore[assignment]
        else:
            data = []

        entry: Optional[Dict[str, Any]] = None
        for item in data:
            if isinstance(item, dict) and item.get("heading_id") == entity_id:
                entry = item
                break
        if entry is None:
            entry = {"heading_id": entity_id, "history": []}
            data.append(entry)

        hist = entry.get("history")
        if not isinstance(hist, list):
            hist = []
            entry["history"] = hist

        event: Dict[str, Any] = {"stage": stage, "decision": decision}
        if metadata:
            # Merge metadata keys at top-level per required example shape.
            for k, v in metadata.items():
                if k in ("stage", "decision"):
                    continue
                event[k] = v
        hist.append(event)

        self.run_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(_json_dumps(data), encoding="utf-8")

    # Backwards compatible helpers (internal use only). These MUST only write allowed files.
    def write_json(self, filename: str, payload: Any) -> None:
        self._assert_allowed(filename)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.path(filename).write_text(_json_dumps(payload), encoding="utf-8")


@dataclass(frozen=True, slots=True)
class NoOpPipelineLogger(PipelineLogger):
    """
    Drop-in replacement for PipelineLogger that writes nothing.
    Used for production runs when logging is disabled.
    """

    def _assert_allowed(self, filename: str) -> None:
        return

    def path(self, filename: str) -> Path:
        return Path("")

    def write_stage(self, stage_name: str, items: List[Any]) -> None:
        return

    def write_stage_payload(self, stage_name: str, payload: Any) -> None:
        return

    def record_decision(
        self,
        entity_id: str,
        stage: str,
        decision: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        return

    def write_json(self, filename: str, payload: Any) -> None:
        return
