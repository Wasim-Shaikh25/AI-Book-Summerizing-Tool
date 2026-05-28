# Operator documentation

| Topic | Location |
|-------|----------|
| **Start here (SDD)** | [`../spec/index.md`](../spec/index.md) |
| Configuration | [`../config/README.md`](../config/README.md) |
| Legacy call-chain docs | [`../doc/spec/README.md`](../doc/spec/README.md) |
| Development tasks | [`../ai-agent-workflow/tasks.md`](../ai-agent-workflow/tasks.md) |

## Running

```bash
python main.py
python -m src.modules.debug.run_toc_trace path/to/book.pdf
```

## Project layout (MESO)

```
spec/           Authoritative design
config/         Tunables (default.yaml)
src/shared/     Config loader, domain models
src/modules/    Feature modules (mirror spec/modules/)
src/utils/      Low-level PDF/OCR helpers
tests/          Unit + integration
scripts/        Pipeline scripts
```

Old import paths (`src.ingestion.*`, `src.structure.*`, etc.) remain as thin compat shims.
