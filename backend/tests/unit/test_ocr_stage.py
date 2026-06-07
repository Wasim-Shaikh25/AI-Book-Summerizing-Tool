"""Unit tests for OCR stage (scanned / two-up PDFs)."""

from __future__ import annotations

from src.modules.ingestion.ocr_stage import (
    is_scanned_page,
    split_page_regions,
    virtual_page_number,
    _synthetic_page_dict,
)


def test_is_scanned_page_low_text():
    page = {"blocks": [{"type": 0, "lines": [{"spans": [{"text": "Hi"}]}]}]}
    assert is_scanned_page(page, [], min_text_chars=40) is True


def test_is_scanned_page_has_text():
    text = "A" * 100
    page = {"blocks": [{"type": 0, "lines": [{"spans": [{"text": text}]}]}]}
    assert is_scanned_page(page, [], min_text_chars=40) is False


def test_split_two_up_regions():
    regions = split_page_regions(1200, 800, split_two_up=True)
    assert len(regions) == 2
    assert regions[0]["side"] == "left"
    assert regions[1]["side"] == "right"
    assert regions[0]["bbox"][2] == 600.0


def test_split_single_page_when_not_two_up():
    regions = split_page_regions(1200, 800, split_two_up=False)
    assert len(regions) == 1
    assert regions[0]["side"] == "full"


def test_virtual_page_numbers_two_up():
    assert virtual_page_number(1, 0, split_two_up=True) == 1
    assert virtual_page_number(1, 1, split_two_up=True) == 2
    assert virtual_page_number(3, 0, split_two_up=True) == 5
    assert virtual_page_number(3, 1, split_two_up=True) == 6


def test_virtual_page_number_no_split():
    assert virtual_page_number(5, 0, split_two_up=False) == 5


def test_synthetic_page_dict_normalizes_x():
    region = {"bbox": [300.0, 0.0, 600.0, 800.0], "side": "right", "width": 300.0}
    lines = [{"text": "Negligence", "bbox": [310.0, 50.0, 400.0, 70.0]}]
    page = _synthetic_page_dict(
        ocr_lines=lines,
        page_number=2,
        region=region,
        source_pdf_page=1,
    )
    assert page["from_ocr"] is True
    assert page["page_number"] == 2
    span = page["blocks"][0]["lines"][0]["spans"][0]
    assert span["bbox"][0] == 10.0  # 310 - 300
