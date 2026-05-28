# Unused / Dead Code Tracking

> MESO Rule 7: After every change, detect unused code. Remove if safe, otherwise log here.
> MESO Rule 3: No unused imports / variables / functions / duplicate logic.

---

## 1. Currently Tracked

| ID | Path | Symbol | Kind | Reason kept | Remove after |
|----|------|--------|------|-------------|--------------|
| U001 | `src/core/candidate_scoring.py` | module | duplicate | Removed during MESO refactor | — |
| U002 | `generation/rewrite.py` | `RewriteEngine` | active | Wired via RewriteModelRouter | — |
| U003 | `handlers/ask_handler.py` | `AskHandler` | stub | Q&A not implemented | Ask feature |
| U004 | `handlers/export_handler.py` | `ExportHandler` | active | Full book Word export | — |
| U005 | `handlers/rewrite_handler.py` | `RewriteHandler` | active | Full book rewrite | — |
| U006 | `src/generation/content_generation.py` | module | empty | Placeholder module | Content gen spec'd |
| U007 | `src/app/__init__.py` | package | empty | Reserved app shell | App layer introduced |
| U008 | `tests/test_*.py` | tests | restored | Re-added in Stage 1 under `tests/unit` + `tests/integration` | — |

---

## 2. Removed (history)

| Date | Path | Symbol | Reason removed |
|------|------|--------|----------------|
| — | `src/LLMAdaptor` | package | LLM structure stages removed; deterministic core only |
| — | LLM validity/TOC stages | pipeline stages | Replaced by deterministic + optional Stage 15b |

---

## 3. Detection Policy

- Run `ruff` / `pytest` on every change.
- Flagged unused items: delete in same change OR log in §1 with removal target.
