"""Apply or skip hierarchy refinement at export time."""

from __future__ import annotations

import copy
from typing import Any, Dict


def hierarchy_already_refined(hierarchy: Dict[str, Any]) -> bool:
    meta = hierarchy.get("meta") or {}
    if meta.get("hierarchy_openai_regrouped"):
        return True
    if meta.get("hierarchy_openai_method"):
        return True
    return False


def refine_hierarchy_for_export(hierarchy: Dict[str, Any]) -> Dict[str, Any]:
    """Run 15h → 15i → 15j only when the hierarchy has not been through 15j yet."""
    if hierarchy_already_refined(hierarchy):
        return hierarchy

    from src.modules.structure.final_structuring.chapter_placement import run_chapter_placement
    from src.modules.structure.final_structuring.hierarchy_openai_refinement import (
        run_hierarchy_openai_refinement,
    )
    from src.modules.structure.final_structuring.subheading_refinement import run_heading_refinement

    return run_hierarchy_openai_refinement(
        run_heading_refinement(run_chapter_placement(copy.deepcopy(hierarchy)))
    )
