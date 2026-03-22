"""
Static analysis helper to identify *candidate* unused Python modules in this repo.

Approach (conservative):
- Treat `main.py` as the runtime entrypoint.
- Parse AST for `import ...` / `from ... import ...` statements.
- Track internal imports under the `src.` namespace.
- Compute reachability from entrypoints via internal imports.
- Report:
  1) Unreached `src.*` modules (candidates for unused)
  2) `src.*` modules with zero internal importers (often unused, but may be loaded dynamically)

Limitations:
- Dynamic imports (importlib, entrypoint registries, config-driven provider selection) are not detected.
- Some modules may be used only in tests or tools; those are not considered “runtime used”.
- Some imports are done inside functions; those are captured (AST walk), but conditional imports may still mislead.
"""

from __future__ import annotations

import ast
import os
from dataclasses import dataclass
from typing import Iterable


def iter_py_files(*roots: str) -> Iterable[str]:
    for root in roots:
        if not os.path.exists(root):
            continue
        if os.path.isfile(root) and root.endswith(".py"):
            yield root
            continue
        for dp, _, fs in os.walk(root):
            for f in fs:
                if f.endswith(".py"):
                    yield os.path.join(dp, f)


def modname(path: str) -> str:
    p = path.replace("\\", "/")
    if p == "main.py":
        return "main"
    if p.startswith("src/"):
        rel = p[len("src/") : -3]
        return "src." + rel.replace("/", ".")
    if p.startswith("tools/"):
        return p[:-3].replace("/", ".")
    if p.startswith("tests/"):
        return p[:-3].replace("/", ".")
    return p[:-3].replace("/", ".")


def imports_in(file_path: str) -> list[str]:
    try:
        txt = open(file_path, "r", encoding="utf-8").read()
        tree = ast.parse(txt, filename=file_path)
    except Exception:
        return []
    out: list[str] = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            for a in n.names:
                out.append(a.name)
        elif isinstance(n, ast.ImportFrom):
            if n.module:
                out.append(n.module)
    return out


@dataclass(frozen=True)
class Report:
    entrypoints: set[str]
    reachable: set[str]
    unused_candidates: list[str]
    zero_internal_importers: list[str]


def build_report(entrypoints: set[str]) -> Report:
    all_files = sorted(set(iter_py_files("main.py", "src", "tools", "tests")))
    file_to_mod = {f: modname(f) for f in all_files}
    mod_to_file = {m: f for f, m in file_to_mod.items()}

    reverse = {m: set() for m in mod_to_file}
    forward = {m: set() for m in mod_to_file}

    for f in all_files:
        fm = file_to_mod[f]
        for imp in imports_in(f):
            if imp == "src" or imp.startswith("src."):
                if imp in mod_to_file:
                    forward[fm].add(imp)
                    reverse[imp].add(fm)
                else:
                    init_mod = imp + ".__init__"
                    if init_mod in mod_to_file:
                        forward[fm].add(init_mod)
                        reverse[init_mod].add(fm)

    reachable = set(entrypoints)
    stack = list(entrypoints)
    while stack:
        cur = stack.pop()
        for nxt in forward.get(cur, set()):
            if nxt not in reachable:
                reachable.add(nxt)
                stack.append(nxt)

    unused_candidates: list[str] = []
    for m in mod_to_file:
        if not m.startswith("src."):
            continue
        if m.endswith(".__init__"):
            continue
        if m not in reachable:
            unused_candidates.append(m)

    zero_internal_importers = sorted(
        [
            m
            for m in mod_to_file
            if m.startswith("src.")
            and not m.endswith(".__init__")
            and len(reverse[m]) == 0
        ]
    )

    return Report(
        entrypoints=entrypoints,
        reachable=reachable,
        unused_candidates=sorted(unused_candidates),
        zero_internal_importers=zero_internal_importers,
    )


def main() -> None:
    entrypoints = {"main"}
    report = build_report(entrypoints)

    all_files = sorted(set(iter_py_files("main.py", "src", "tools", "tests")))
    file_to_mod = {f: modname(f) for f in all_files}
    mod_to_file = {m: f for f, m in file_to_mod.items()}

    print("ENTRYPOINTS:", sorted(report.entrypoints))
    print(
        "REACHABLE src.* MODULES:",
        len([m for m in report.reachable if m.startswith("src.")]),
    )

    print("\nUNREACHED src.* MODULES (candidates):")
    for m in report.unused_candidates:
        print(f"- {m:50s} ({mod_to_file[m]})")

    print("\nsrc.* MODULES WITH ZERO INTERNAL IMPORTERS:")
    for m in report.zero_internal_importers:
        print(f"- {m:50s} ({mod_to_file[m]})")

    print(
        "\nNOTE: This is a static scan. Provider selection / handler registries may load modules dynamically."
    )


if __name__ == "__main__":
    main()
