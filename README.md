# AI Notes Creator Model

PDF book structure extraction and optional AI-assisted note generation.

> Engineered under the **MESO Universal Engineering Standard**.  
> **Start here:** [`spec/index.md`](./spec/index.md)

---

## Quick Map

| Directory | Purpose |
|-----------|---------|
| [`spec/`](./spec/index.md) | Authoritative SDD (start every task here) |
| [`config/`](./config/README.md) | Tunables — `default.yaml` (MESO Rule 12) |
| [`src/shared/`](./src/shared/) | Config loader, domain models |
| [`src/modules/`](./src/modules/) | Feature modules (mirror `spec/modules/`) |
| [`docs/`](./docs/README.md) | Operator documentation |
| [`tests/`](./tests/README.md) | Unit / integration tests |
| [`ai-agent-workflow/`](./ai-agent-workflow/) | Requirements, tasks |
| [`scripts/`](./scripts/) | Pipeline scripts |

Legacy import paths (`src.ingestion.*`, `src.core.*`) remain as compat shims.

---

## Entry Points

```bash
# Interactive CLI
python main.py

# Debug pipeline trace (logs + DB)
python -m src.modules.debug.run_toc_trace path/to/book.pdf

# Canonical import
from src.modules.pipeline import run_pipeline
from src.book_pipeline import run_pipeline  # stable alias
```

---

## Configuration

1. Copy `.env.example` → `.env` for secrets and overrides.
2. Defaults live in [`config/default.yaml`](./config/default.yaml).
3. Loader: [`src/shared/config.py`](./src/shared/config.py).

See [`spec/modules/parameters-config.md`](./spec/modules/parameters-config.md).

---

## Contribution Discipline (MESO)

1. Read [`spec/index.md`](./spec/index.md)
2. Update relevant spec module **first**
3. Implement code under `src/modules/` or `src/shared/`
4. Append [`spec/change-log.md`](./spec/change-log.md)
