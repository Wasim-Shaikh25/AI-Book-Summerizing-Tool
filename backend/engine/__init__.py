"""
Engine package shim — canonical pipeline/structure/ingestion code.

Incremental rename target for ``backend/src/modules/``.
Existing imports via ``src.modules.*`` remain supported.
"""

from src.modules.pipeline import run_pipeline
from src.modules.pipeline.stage_registry import (
    STAGE_CLEAN_TITLES,
    STAGE_GROUP_CHAPTERS,
    STAGE_PARTITION_SECTIONS,
    STAGE_VALIDATE_TITLES,
    # Deprecated numeric aliases
    STAGE_15D,
    STAGE_15E,
    STAGE_15F,
    STAGE_15G,
    resolve_existing_artifact,
    require_artifact,
)

__all__ = [
    "run_pipeline",
    "STAGE_PARTITION_SECTIONS",
    "STAGE_GROUP_CHAPTERS",
    "STAGE_CLEAN_TITLES",
    "STAGE_VALIDATE_TITLES",
    "STAGE_15D",
    "STAGE_15E",
    "STAGE_15F",
    "STAGE_15G",
    "resolve_existing_artifact",
    "require_artifact",
]
