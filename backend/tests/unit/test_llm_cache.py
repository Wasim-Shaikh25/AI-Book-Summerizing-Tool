"""Tests for the content-hash LLM completion cache (cost reduction)."""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND_ROOT))

from src.shared import llm_cache  # noqa: E402


def test_cache_hit_avoids_second_llm_call(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LLM_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("REWRITE_CACHE_ENABLED", "1")

    calls = {"n": 0}

    def _generate(system: str, user: str) -> str:
        calls["n"] += 1
        return f"notes for {user}"

    wrapped = llm_cache.cached_generate(_generate, max_tokens=100)

    first = wrapped("SYS", "Rewrite section A")
    second = wrapped("SYS", "Rewrite section A")

    assert first == second == "notes for Rewrite section A"
    assert calls["n"] == 1  # second call served from cache


def test_cache_key_changes_with_inputs(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LLM_CACHE_DIR", str(tmp_path))
    k1 = llm_cache.cache_key(system="S", user="A", max_tokens=100)
    k2 = llm_cache.cache_key(system="S", user="B", max_tokens=100)
    k3 = llm_cache.cache_key(system="S", user="A", max_tokens=200)
    assert k1 != k2
    assert k1 != k3


def test_disable_flag_bypasses_cache(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LLM_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("REWRITE_CACHE_ENABLED", "0")

    calls = {"n": 0}

    def _generate(system: str, user: str) -> str:
        calls["n"] += 1
        return "out"

    wrapped = llm_cache.cached_generate(_generate, max_tokens=50)
    wrapped("S", "U")
    wrapped("S", "U")
    assert calls["n"] == 2  # caching disabled -> both call through
