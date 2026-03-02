from typing import Any

from src.config import DEBUG_STRUCTURE


def debug_log(title: str, data: Any = None):
    if not DEBUG_STRUCTURE:
        return

    print("\n" + "=" * 80)
    print(f"[DEBUG] {title}")
    print("=" * 80)

    if data is None:
        return

    if isinstance(data, (dict, list)):
        import json

        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print(str(data))
