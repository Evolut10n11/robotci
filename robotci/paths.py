from __future__ import annotations

from pathlib import Path


def state_dir(project_root: str | Path | None = None) -> Path:
    root = Path.cwd() if project_root is None else Path(project_root)
    return root / ".robotci"


def result_path(project_root: str | Path | None = None) -> Path:
    return state_dir(project_root) / "result.json"
