"""Clone the tool into a project folder (one graph per project) and initialise its database."""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Optional

TOOL_ITEMS = ("codegraph", "ui", "tests", "cg.py", "requirements.txt", "README.md")
CLAUDE_ITEMS = ("skills/code-graph", "skills/c4-design", "skills/orchestrate-cycle", "agents", "playbooks")
IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache", "code_graph.db*")


def _copy_tree(src: Path, dst: Path, force: bool, report: list[str]) -> None:
    if src.is_file():
        if force or not dst.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            report.append(str(dst))
        return
    for item in src.rglob("*"):
        if item.is_dir() or IGNORE(str(item.parent), [item.name]) or {"__pycache__", ".pytest_cache"} & set(item.parts):
            continue
        _copy_tree(item, dst / item.relative_to(src), force, report)


def install(tool_dir: Path, project_dir: Path, *, name: Optional[str] = None, with_claude: bool = False,
            force: bool = False) -> dict:
    from .db import connect
    from .service import GraphService

    project_dir = project_dir.resolve()
    if not project_dir.is_dir():
        raise FileNotFoundError(f"project folder not found: {project_dir}")
    dest = project_dir / "code_graph"
    copied: list[str] = []
    for item in TOOL_ITEMS:
        if (tool_dir / item).exists():
            _copy_tree(tool_dir / item, dest / item, force, copied)
    if with_claude:
        claude_src = tool_dir.parent / ".claude"
        for item in CLAUDE_ITEMS:
            if (claude_src / item).exists():
                _copy_tree(claude_src / item, project_dir / ".claude" / item, force, copied)

    db_path = dest / "code_graph.db"
    conn = connect(str(db_path))
    try:
        svc = GraphService(conn)
        if not svc.repo.get_meta("project"):
            svc.init_project(name or project_dir.name, actor="installer")
        project = svc.repo.get_meta("project")
    finally:
        conn.close()
    return {"installed_to": str(dest), "db": str(db_path), "project": project, "files_copied": len(copied),
            "next": [f"python {dest / 'cg.py'} serve --port 8770", f"python {dest / 'cg.py'} import <c4_seed.json>"]}
