# Configuration

All tunables for the AI Notes Creator Model live in this directory (MESO Rule 12).

| File | Purpose |
|------|---------|
| [`default.yaml`](./default.yaml) | Base defaults (non-secret) |
| [`.env.example`](../.env.example) | Secret keys and env overrides |

Runtime loader: [`src/shared/config.py`](../src/shared/config.py)

Overlay order: **`default.yaml` → environment variables → `.env`**
