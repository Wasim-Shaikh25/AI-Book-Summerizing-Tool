from __future__ import annotations

import sys
from pathlib import Path


# Ensure `import src...` works when running pytest from repo root on Windows.
# This is intentionally minimal and test-only plumbing (no architecture changes).
REPO_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
