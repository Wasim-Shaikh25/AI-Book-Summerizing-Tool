#!/usr/bin/env python3
"""Move backend/logs and backend/output into repo-root logs/ and output/."""

from __future__ import annotations

import shutil
import sys
from datetime import datetime
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
_ROOT = _BACKEND.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


def _merge_tree(src: Path, dest: Path) -> int:
    if not src.exists():
        return 0
    moved = 0
    dest.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        target = dest / item.name
        if item.is_dir():
            moved += _merge_tree(item, target)
            try:
                item.rmdir()
            except OSError:
                pass
        else:
            if target.exists():
                if item.stat().st_mtime > target.stat().st_mtime:
                    backup = target.with_suffix(target.suffix + ".bak")
                    if not backup.exists():
                        shutil.copy2(target, backup)
                    shutil.copy2(item, target)
                item.unlink(missing_ok=True)
            else:
                shutil.move(str(item), str(target))
            moved += 1
    return moved


def _backup_if_exists(path: Path) -> None:
    if path.exists():
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = path.with_name(f"{path.name}.bak_{stamp}")
        shutil.copy2(path, backup)
        print(f"Backed up {path} -> {backup}")


def main() -> int:
    backend_logs = _BACKEND / "logs"
    backend_output = _BACKEND / "output"
    root_logs = _ROOT / "logs"
    root_output = _ROOT / "output"

    root_logs.mkdir(parents=True, exist_ok=True)
    root_output.mkdir(parents=True, exist_ok=True)

    log_moves = _merge_tree(backend_logs, root_logs)
    print(f"Merged logs: {log_moves} items from {backend_logs} -> {root_logs}")

    for sub in ("uploads", "exports", "rag_index"):
        n = _merge_tree(backend_output / sub, root_output / sub)
        if n:
            print(f"Merged {sub}: {n} items")

    src_db = backend_output / "knowledge_base.db"
    dest_db = root_output / "knowledge_base.db"
    if src_db.exists():
        _backup_if_exists(dest_db)
        shutil.copy2(src_db, dest_db)
        print(f"Copied active DB {src_db} -> {dest_db}")

    # Normalize DB paths to project-relative posix
    if dest_db.exists():
        import sqlite3

        from src.shared.paths import resolve_project_path, to_project_relative_path

        conn = sqlite3.connect(dest_db)
        cur = conn.cursor()
        try:
            cur.execute("SELECT user_id, book_id, file_path, log_dir FROM user_books")
            rows = cur.fetchall()
            for user_id, book_id, file_path, log_dir in rows:
                resolved_fp = resolve_project_path(file_path) if file_path else None
                resolved_log = resolve_project_path(log_dir) if log_dir else None
                new_fp = to_project_relative_path(resolved_fp) if resolved_fp else file_path
                new_log = to_project_relative_path(resolved_log) if resolved_log else log_dir
                if new_fp != file_path or new_log != log_dir:
                    cur.execute(
                        "UPDATE user_books SET file_path = ?, log_dir = ? WHERE user_id = ? AND book_id = ?",
                        (new_fp, new_log, user_id, book_id),
                    )
            conn.commit()
            print(f"Normalized {len(rows)} user_books path(s) in DB")
        except sqlite3.Error as exc:
            print(f"DB normalize skipped: {exc}")
        finally:
            conn.close()

    for leftover in (backend_logs, backend_output):
        if leftover.exists():
            try:
                shutil.rmtree(leftover)
                print(f"Removed {leftover}")
            except OSError as exc:
                print(f"Could not remove {leftover}: {exc}")

    print("Done. Runtime data is under repo-root logs/ and output/.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
