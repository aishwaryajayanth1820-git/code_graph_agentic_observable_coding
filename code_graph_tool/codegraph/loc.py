"""Lines-of-code measurement for node code paths.

code_path forms:  `src/pkg/module.py::ClassName` | `src/pkg/module.py` | `src/pkg` (directory).
Extension point: register a counter for a new language in COUNTERS.
"""
from __future__ import annotations

import ast
from pathlib import Path
from typing import Callable, Optional

SOURCE_EXTENSIONS = {".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".kt", ".cs", ".go", ".rs", ".sql"}


def _code_lines(text: str, comment_prefixes: tuple[str, ...]) -> int:
    return sum(1 for line in text.splitlines() if line.strip() and not line.strip().startswith(comment_prefixes))


def _python(path: Path, symbol: Optional[str]) -> int:
    text = path.read_text(encoding="utf-8", errors="ignore")
    if symbol:
        try:
            for node in ast.walk(ast.parse(text)):
                if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == symbol:
                    lines = text.splitlines()[node.lineno - 1: node.end_lineno]
                    return _code_lines("\n".join(lines), ("#",))
        except SyntaxError:
            pass
    return _code_lines(text, ("#",))


def _generic(path: Path, symbol: Optional[str]) -> int:
    return _code_lines(path.read_text(encoding="utf-8", errors="ignore"), ("//", "#", "--", "*", "/*"))


COUNTERS: dict[str, Callable[[Path, Optional[str]], int]] = {".py": _python}


def count_loc(project_root: Path, code_path: Optional[str]) -> Optional[int]:
    if not code_path:
        return None
    rel, _, symbol = code_path.partition("::")
    target = (project_root / rel).resolve()
    if target.is_file():
        return COUNTERS.get(target.suffix, _generic)(target, symbol or None)
    if target.is_dir():
        files = [p for p in target.rglob("*") if p.is_file() and p.suffix in SOURCE_EXTENSIONS
                 and "__pycache__" not in p.parts and "node_modules" not in p.parts]
        return sum(COUNTERS.get(p.suffix, _generic)(p, None) for p in files)
    return None
