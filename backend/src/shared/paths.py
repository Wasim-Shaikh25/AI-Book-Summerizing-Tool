"""Resolve runtime file paths under PROJECT_ROOT."""

from __future__ import annotations

from pathlib import Path

from src.shared.config import BASE_DIR


def _normalize_stored_path(path: str | Path) -> Path:
    """Resolve any stored path against PROJECT_ROOT (never cwd)."""
    root = Path(BASE_DIR).resolve()
    raw = Path(path)
    posix = raw.as_posix().replace("\\", "/")
    if posix.startswith("backend/"):
        posix = posix[len("backend/") :]
    if raw.is_absolute():
        return raw.resolve()
    return (root / posix).resolve()


def to_project_relative_path(path: str | Path) -> str:
    """Store paths relative to PROJECT_ROOT (e.g. output/uploads/...)."""
    p = _normalize_stored_path(path)
    root = Path(BASE_DIR).resolve()
    try:
        rel = p.relative_to(root)
        return rel.as_posix()
    except ValueError:
        return p.as_posix()


def resolve_project_path(path: str | Path | None) -> Path | None:
    """Resolve a stored path against PROJECT_ROOT (with legacy backend/ prefix)."""
    if not path:
        return None

    root = Path(BASE_DIR).resolve()
    posix = Path(path).as_posix().replace("\\", "/")
    candidates = [
        _normalize_stored_path(path),
        (root / "backend" / Path(path)).resolve(),
    ]
    if posix.startswith("backend/"):
        candidates.insert(0, (root / posix[len("backend/") :]).resolve())

    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key in seen:
            continue
        seen.add(key)
        if candidate.exists():
            return candidate

    return candidates[0]
