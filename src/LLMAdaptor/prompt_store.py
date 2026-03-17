from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Tuple


@dataclass(frozen=True)
class PromptBundle:
    key: str
    system: str
    user: str


class PromptStore:
    """
    Loads shared prompts from one folder with a single naming convention.

    Convention:
      {key}.system.txt
      {key}.user.txt

    Example:
      heading_validity.system.txt
      heading_validity.user.txt
    """

    def __init__(self, prompts_dir: Path):
        self._dir = prompts_dir
        self._cache: Dict[str, PromptBundle] = {}

    def _paths_for_key(self, key: str) -> Tuple[Path, Path]:
        sys_path = self._dir / f"{key}.system.txt"
        user_path = self._dir / f"{key}.user.txt"
        return sys_path, user_path

    def get(self, key: str) -> PromptBundle:
        if key in self._cache:
            return self._cache[key]

        sys_path, user_path = self._paths_for_key(key)
        if not sys_path.exists():
            raise FileNotFoundError(f"Missing system prompt file: {sys_path.as_posix()}")
        if not user_path.exists():
            raise FileNotFoundError(f"Missing user prompt file: {user_path.as_posix()}")

        bundle = PromptBundle(
            key=key,
            system=sys_path.read_text(encoding="utf-8"),
            user=user_path.read_text(encoding="utf-8"),
        )
        self._cache[key] = bundle
        return bundle
