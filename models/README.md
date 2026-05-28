# Local model weights

GGUF and other large model files are **not** stored in git.

Download models separately and place them here, then set paths in `.env`:

| Variable | Example |
|----------|---------|
| `LLAMACPP_MODEL_PATH` | `models/Qwen2.5-3B-Instruct-Q4_K_M.gguf` |

Supported layouts follow `config/default.yaml` and `spec/modules/parameters-config.md`.
