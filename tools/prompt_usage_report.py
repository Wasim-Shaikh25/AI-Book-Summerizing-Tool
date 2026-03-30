"""
Generate a conservative prompt-usage report.

This repo stores prompts in `src/LLMAdaptor/prompts` using `{key}.system.txt` and `{key}.user.txt`.
We scan Python sources for literal uses of:
  - LLMClient.from_config().generate("<key>", ...)
  - client.prompts.get("<key>")
"""

from __future__ import annotations

import glob
import json
import os
import re
from pathlib import Path


def main() -> None:
    prompt_files = glob.glob("src/LLMAdaptor/prompts/*.txt")
    keys = sorted(
        {
            os.path.basename(p)
            .replace(".system.txt", "")
            .replace(".user.txt", "")
            for p in prompt_files
        }
    )

    used: set[str] = set()
    py_files = glob.glob("src/**/*.py", recursive=True)
    for py in py_files:
        if py.startswith("venv") or "\\venv\\" in py:
            continue
        s = Path(py).read_text(encoding="utf-8", errors="ignore")

        for m in re.finditer(r"\.generate\(\s*['\"]([a-z0-9_]+)['\"]", s):
            used.add(m.group(1))
        for m in re.finditer(r"prompts\.get\(\s*['\"]([a-z0-9_]+)['\"]", s):
            used.add(m.group(1))

    unused = sorted(set(keys) - used)

    out = {
        "prompt_keys_on_disk": keys,
        "used_keys_literal": sorted(used),
        "unused_keys_literal": unused,
        "prompt_files": sorted(prompt_files),
    }

    out_path = Path("output/prompt_usage_report.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")

    print(out_path.as_posix())
    print("unused_keys_literal:", unused)


if __name__ == "__main__":
    main()
