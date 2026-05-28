"""Backward-compatible domain shim. Prefer: from src.shared.models import ..."""

from src.shared.models import (  # noqa: F401
    FinalHeading,
    Fragment,
    HeadingCandidate,
    NormalizedLine,
    PipelineResult,
)
