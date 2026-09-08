"""DOCX color palettes — study (color) vs elegant black & white."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Tuple

from docx.shared import Pt, RGBColor


@dataclass(frozen=True, slots=True)
class DocxThemePalette:
    name: str
    text: RGBColor
    text_muted: RGBColor
    h1_color: RGBColor
    h2_color: RGBColor
    h3_color: RGBColor
    h1_border: str
    h2_border: str
    h3_border: str
    header_band_fill: str
    table_header_fill: str
    table_alt_fill: str
    table_header_text: RGBColor
    callout_default: Tuple[str, str, RGBColor]
    callout_styles: Dict[str, Tuple[str, str, RGBColor]] = field(default_factory=dict)
    cover_title_color: RGBColor | None = None
    toc_title_color: RGBColor | None = None

    @property
    def cover_title(self) -> RGBColor:
        return self.cover_title_color or self.h1_color

    @property
    def toc_title(self) -> RGBColor:
        return self.toc_title_color or self.h1_color


_COLOR = DocxThemePalette(
    name="color",
    text=RGBColor(0x32, 0x31, 0x30),
    text_muted=RGBColor(0x60, 0x5E, 0x5C),
    h1_color=RGBColor(0x5C, 0x2D, 0x91),
    h2_color=RGBColor(0x00, 0x88, 0x82),
    h3_color=RGBColor(0x00, 0x5A, 0x9E),
    h1_border="5C2D91",
    h2_border="008882",
    h3_border="0078D4",
    header_band_fill="5C2D91",
    table_header_fill="E8F4FC",
    table_alt_fill="F8FBFE",
    table_header_text=RGBColor(0x00, 0x5A, 0x9E),
    callout_default=("F3F9FD", "B4D6FA", RGBColor(0x00, 0x5A, 0x9E)),
    callout_styles={
        "course outcomes": ("F5F0FA", "C4B5FD", RGBColor(0x5C, 0x2D, 0x91)),
        "learning objectives": ("F5F0FA", "C4B5FD", RGBColor(0x5C, 0x2D, 0x91)),
        "key points": ("F3F9FD", "B4D6FA", RGBColor(0x00, 0x78, 0xD4)),
        "quick revision": ("FFF9E6", "F5D76E", RGBColor(0xC4, 0x9A, 0x00)),
        "definition": ("F0FAF4", "A8D5BA", RGBColor(0x10, 0x7C, 0x41)),
        "important": ("FFF4F0", "F5B8A8", RGBColor(0xC4, 0x3E, 0x1C)),
        "note": ("F8F8F8", "D0D0D0", RGBColor(0x60, 0x5E, 0x5C)),
        "summary": ("F3F9FD", "B4D6FA", RGBColor(0x00, 0x5A, 0x9E)),
        "exam tip": ("FFF9E6", "F5D76E", RGBColor(0xC4, 0x9A, 0x00)),
    },
)

_BW = DocxThemePalette(
    name="bw",
    text=RGBColor(0x1A, 0x1A, 0x1A),
    text_muted=RGBColor(0x4A, 0x4A, 0x4A),
    h1_color=RGBColor(0x00, 0x00, 0x00),
    h2_color=RGBColor(0x1A, 0x1A, 0x1A),
    h3_color=RGBColor(0x2E, 0x2E, 0x2E),
    h1_border="000000",
    h2_border="333333",
    h3_border="666666",
    header_band_fill="1A1A1A",
    table_header_fill="E8E8E8",
    table_alt_fill="F5F5F5",
    table_header_text=RGBColor(0x00, 0x00, 0x00),
    callout_default=("F5F5F5", "333333", RGBColor(0x00, 0x00, 0x00)),
    callout_styles={
        "course outcomes": ("F0F0F0", "000000", RGBColor(0x00, 0x00, 0x00)),
        "learning objectives": ("F0F0F0", "000000", RGBColor(0x00, 0x00, 0x00)),
        "key points": ("F5F5F5", "333333", RGBColor(0x00, 0x00, 0x00)),
        "quick revision": ("FAFAFA", "666666", RGBColor(0x1A, 0x1A, 0x1A)),
        "definition": ("F3F3F3", "444444", RGBColor(0x00, 0x00, 0x00)),
        "important": ("EEEEEE", "000000", RGBColor(0x00, 0x00, 0x00)),
        "note": ("F8F8F8", "AAAAAA", RGBColor(0x4A, 0x4A, 0x4A)),
        "summary": ("F0F0F0", "333333", RGBColor(0x00, 0x00, 0x00)),
        "exam tip": ("FAFAFA", "666666", RGBColor(0x1A, 0x1A, 0x1A)),
    },
    cover_title_color=RGBColor(0x00, 0x00, 0x00),
    toc_title_color=RGBColor(0x00, 0x00, 0x00),
)

THEMES: dict[str, DocxThemePalette] = {
    "color": _COLOR,
    "colour": _COLOR,
    "study": _COLOR,
    "colorful": _COLOR,
    "bw": _BW,
    "b&w": _BW,
    "black_white": _BW,
    "black-white": _BW,
    "monochrome": _BW,
    "grayscale": _BW,
}


def normalize_theme_name(name: str | None) -> str:
    key = (name or "color").strip().lower().replace(" ", "_")
    if key in THEMES:
        return THEMES[key].name
    return "color"


def get_palette(name: str | None = None) -> DocxThemePalette:
    key = (name or "color").strip().lower().replace(" ", "_")
    return THEMES.get(key, _COLOR)
