"""Tests for English-only text policy."""

from __future__ import annotations

import os

import pytest

from src.shared import english_text as et


@pytest.fixture(autouse=True)
def _english_only_on(monkeypatch):
    monkeypatch.setenv("ENGLISH_ONLY", "1")
    monkeypatch.setattr(et, "english_only_enabled", lambda: True)


def test_strip_to_english_removes_devanagari():
    assert et.strip_to_english("Divorce (िमसाल)") == "Divorce ()"
    assert et.strip_to_english("परिचय") == ""


def test_filter_english_line_discards_pure_hindi():
    assert et.filter_english_line("परिचय") == ""
    assert et.filter_english_line("Introduction to Family Law") == "Introduction to Family Law"


def test_is_primarily_english_rejects_non_latin():
    assert not et.is_primarily_english("परिचय")
    assert et.is_primarily_english("Citizenship by descent (Art. 5)")


def test_filter_english_heading():
    assert et.filter_english_heading("Marriage and Divorce") == "Marriage and Divorce"
    assert et.filter_english_heading("?????)") is None
    assert et.filter_english_heading("िमसाल)") is None


def test_filter_english_body_drops_non_english_lines():
    body = "Valid English line\nपरिचय\nAnother English line"
    out = et.filter_english_body(body)
    assert "Valid English line" in out
    assert "Another English line" in out
    assert "परिचय" not in out


def test_english_only_disabled(monkeypatch):
    monkeypatch.setenv("ENGLISH_ONLY", "0")
    monkeypatch.setattr(et, "english_only_enabled", lambda: False)
    assert et.filter_english_line("परिचय") == "परिचय"
    assert et.english_only_rewrite_instruction() == ""


def test_rule_reject_reason_non_english():
    from src.modules.structure.heading_title_validation import rule_reject_reason

    assert rule_reject_reason("िमसाल)") == "non_english"
    assert rule_reject_reason("?????)") == "non_english"
    assert rule_reject_reason("Fundamental Rights") is None


def test_dropped_registry_rejects_non_english():
    from src.modules.structure.dropped_heading_registry import DroppedHeadingRegistry

    reg = DroppedHeadingRegistry()
    assert not reg.is_allowed_title("परिचय")
    assert reg.is_allowed_title("Fundamental Rights")
