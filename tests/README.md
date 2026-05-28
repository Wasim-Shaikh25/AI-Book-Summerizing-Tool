# Tests

MESO traceability: module specs map to tests under `unit/` and `integration/`.

| Test file | Covers |
|-----------|--------|
| `unit/test_heading_validator_heuristics.py` | `heading_heuristics` |
| `unit/test_continuity_and_gate.py` | `continuity_filter`, gate helpers |
| `integration/test_logging_contract.py` | `PipelineLogger` stage JSON contract |
| `integration/test_fragment_coverage.py` | fragments + SQLite persistence |

## Fixture PDF

Bundled sample: `src/modules/debug/pdf_files/The Law of Torts 2018 by Jhabwala.pdf`

## Run

```bash
# Unit only (fast)
pytest tests/unit -q

# Integration (uses bundled PDF, ~1–2 min)
pytest tests/integration -m integration -q

# All
pytest tests -q
```

Integration tests run in an isolated temp cwd (see `tests/conftest.py`).
