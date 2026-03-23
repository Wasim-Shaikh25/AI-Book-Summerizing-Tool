from __future__ import annotations

import ast
import pathlib
from collections import defaultdict
from typing import DefaultDict, Iterable


def iter_py_files(root: str = "src") -> Iterable[pathlib.Path]:
    return pathlib.Path(root).rglob("*.py")


def module_name_from_path(path: pathlib.Path) -> str:
    # path like src/structure/noise_filter.py -> src.structure.noise_filter
    parts = list(path.as_posix().split("/"))
    if not parts or parts[0] != "src":
        raise ValueError(f"Expected path under src/: {path}")
    mod_parts = parts[:-1] + [parts[-1].removesuffix(".py")]
    return ".".join(mod_parts)


def iter_imports(path: pathlib.Path) -> Iterable[str]:
    """
    Yield imported module names (as written) for:
      - import x
      - import x as y
      - from x import y
      - from x.y import z

    Notes:
      - This is static and ignores runtime/dynamic imports.
      - For `from . import foo`, ast gives module=None and level>0; we skip those.
        (relative imports can be resolved later if needed).
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
    except SyntaxError:
        return []

    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name:
                    out.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                out.append(node.module)
    return out


def build_graph() -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    """
    Returns:
      - imports_by_module: module -> set(imported_module_prefixes)
      - importers_by_module: imported_module_prefix -> set(importer_modules)
    """
    imports_by_module: dict[str, set[str]] = {}
    importers_by_module: DefaultDict[str, set[str]] = defaultdict(set)

    for p in iter_py_files("src"):
        mod = module_name_from_path(p)
        imports = set(iter_imports(p))
        imports_by_module[mod] = imports
        for imp in imports:
            # record exact import string
            importers_by_module[imp].add(mod)

    return imports_by_module, dict(importers_by_module)


def main() -> None:
    imports_by_module, importers_by_module = build_graph()

    all_modules = sorted(imports_by_module.keys())

    # "Internal" modules are those whose name starts with src.
    internal_modules = [m for m in all_modules if m.startswith("src.")]
    internal_set = set(internal_modules)

    # Resolve importers to internal-only by exact match or by prefix (common case: import src.structure)
    internal_importers: DefaultDict[str, set[str]] = defaultdict(set)
    for imported, importers in importers_by_module.items():
        if not imported.startswith("src"):
            continue
        # If someone imports src.structure, it might cover src.structure.noise_filter at runtime,
        # but python won't auto-import submodules. So we keep "exact import string" as is.
        for imp in importers:
            internal_importers[imported].add(imp)

    # Compute modules with zero internal importers (exact-string based)
    zero_internal_importers = []
    for m in internal_modules:
        if m not in internal_importers:
            zero_internal_importers.append(m)

    print(f"TOTAL src/**/*.py modules: {len(all_modules)}")
    print(f"TOTAL internal modules (src.*): {len(internal_modules)}")
    print()
    print("MODULES WITH ZERO INTERNAL IMPORTERS (exact import string match):")
    for m in sorted(zero_internal_importers):
        print("-", m)


if __name__ == "__main__":
    main()
