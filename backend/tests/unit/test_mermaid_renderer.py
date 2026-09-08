"""Tests for mermaid diagram rendering."""
from __future__ import annotations

from pathlib import Path

from docx import Document

from src.modules.export.docx_notes_exporter import append_markdown_body
from src.modules.export.mermaid_renderer import (
    _fit_picture_dimensions,
    _parse_flowchart,
    _strip_diagram_heading_markdown,
    compute_diagram_display_size,
    iter_markdown_segments,
    render_mermaid_to_png,
    shrink_diagram_to_page_flow,
)


def test_iter_markdown_segments_splits_mermaid() -> None:
    text = """### Key Points
- Fact one

```mermaid
flowchart TD
    A[Start] --> B[End]
```

More text."""
    kinds = [s.kind for s in iter_markdown_segments(text)]
    assert kinds == ["markdown", "mermaid", "markdown"]


def test_parse_flowchart_extracts_nodes_and_edges() -> None:
    nodes, edges = _parse_flowchart(
        "flowchart TD\n    A[Preamble] --> B[Fundamental Rights]\n    B --> C[DPSP]"
    )
    assert len(nodes) == 3
    assert ("A", "Preamble") in nodes
    assert ("A", "B") in edges


def test_render_mermaid_to_png_pillow_fallback(tmp_path: Path) -> None:
    src = "flowchart TD\n    A[India] --> B[States]\n    B --> C[Union]"
    out = tmp_path / "diagram.png"
    ok = render_mermaid_to_png(src, out, allow_network=False)
    assert ok is True
    assert out.exists()
    assert out.stat().st_size > 100


def test_strip_standalone_diagram_heading() -> None:
    text = "### Key Points\n- One\n\n### Diagram\n\nMore"
    out = _strip_diagram_heading_markdown(text)
    assert "### Diagram" not in out
    assert "Key Points" in out


def test_shrink_diagram_to_page_flow_reduces_oversized_height() -> None:
    w, h = shrink_diagram_to_page_flow(5.0, 6.0, page_body_height_in=8.0)
    assert h < 6.0
    assert w < 5.0
    assert h <= 8.0 * 0.68


def test_compute_diagram_display_size_scales_simple_diagram_up(tmp_path: Path) -> None:
    from PIL import Image

    path = tmp_path / "small.png"
    Image.new("RGB", (520, 280), "white").save(path)
    src = "flowchart TD\n    A[Equality] --> B[Law]\n    B --> C[State]"
    w, h = compute_diagram_display_size(path, src)
    assert w >= 4.0
    assert h >= 2.0


def test_fit_picture_dimensions_caps_tall_image(tmp_path: Path) -> None:
    from PIL import Image

    path = tmp_path / "tall.png"
    Image.new("RGB", (400, 1200), "white").save(path)
    w, h = _fit_picture_dimensions(path, max_width_in=3.0, max_height_in=2.0)
    assert w <= 3.01
    assert h <= 2.01


def test_append_markdown_body_embeds_diagram_image(tmp_path: Path) -> None:
    doc = Document()
    body = """### Diagram
```mermaid
flowchart TD
    A[One] --> B[Two]
```"""
    append_markdown_body(doc, body, assets_dir=tmp_path)
    assert any("graphic" in p._element.xml for p in doc.paragraphs)
