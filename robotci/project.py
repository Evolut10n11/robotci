from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

DEFAULT_CONFIG_PATH = Path("robotci.yaml")


@dataclass(frozen=True)
class ProjectContext:
    """Resolved user-project paths shared by validate, plan and run."""

    project_root: Path
    config_path: Path


def resolve_project_context(
    config_path: str | Path = DEFAULT_CONFIG_PATH,
    *,
    project_root: str | Path | None = None,
) -> ProjectContext:
    """Resolve a config without falling back to RobotCI's own checkout.

    An explicit project root anchors relative paths. Otherwise an existing
    relative config is searched for from the current directory through its
    parents. An absolute config, including the path printed by ``robotci-init``,
    makes its containing directory the project root.
    """

    anchor = (
        Path.cwd()
        if project_root is None
        else Path(project_root).expanduser()
    ).resolve()
    requested = Path(config_path).expanduser()

    if requested.is_absolute():
        resolved_config = requested.resolve()
        resolved_root = anchor if project_root is not None else resolved_config.parent
        return ProjectContext(resolved_root, resolved_config)

    if project_root is not None:
        return ProjectContext(anchor, (anchor / requested).resolve())

    for candidate in (anchor, *anchor.parents):
        resolved_config = (candidate / requested).resolve()
        if resolved_config.is_file():
            return ProjectContext(resolved_config.parent, resolved_config)

    resolved_config = (anchor / requested).resolve()
    return ProjectContext(resolved_config.parent, resolved_config)
