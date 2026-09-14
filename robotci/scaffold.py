from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile

from robotci.config import ConfigError, load_config

DEFAULT_CONFIG_FILENAME = "robotci.yaml"
DEFAULT_CONFIG_TEXT = """version: 1
runtime: auto

scenarios:
  - name: smoke_route
    map_id: nav2-loopback
    start:
      x: 0.0
      y: 0.0
      yaw: 0.0
    goal:
      x: 1.0
      y: 0.0
      yaw: 0.0
    timeout_sec: 60
"""


class ScaffoldError(ValueError):
    """Raised when RobotCI project scaffolding cannot be completed safely."""


@dataclass(frozen=True)
class ScaffoldResult:
    project_root: Path
    config_path: Path
    replaced: bool


def render_starter_config() -> str:
    """Return the deterministic starter RobotCI configuration."""
    return DEFAULT_CONFIG_TEXT


def initialize_project(
    project_root: str | Path | None = None,
    *,
    force: bool = False,
) -> ScaffoldResult:
    """Create a validated starter ``robotci.yaml`` in an existing project directory."""
    root = Path.cwd() if project_root is None else Path(project_root).expanduser()
    root = root.resolve()

    if not root.exists():
        raise ScaffoldError(f"project root does not exist: {root}")
    if not root.is_dir():
        raise ScaffoldError(f"project root is not a directory: {root}")

    config_path = root / DEFAULT_CONFIG_FILENAME
    replaced = config_path.exists()
    if replaced and not force:
        raise ScaffoldError(
            f"RobotCI config already exists: {config_path}; use --force to replace it"
        )

    temporary_path: Path | None = None
    try:
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            prefix=".robotci-init-",
            suffix=".yaml",
            dir=root,
            delete=False,
        ) as handle:
            handle.write(render_starter_config())
            temporary_path = Path(handle.name)

        load_config(temporary_path)
        temporary_path.replace(config_path)
    except (ConfigError, OSError) as exc:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
        raise ScaffoldError(f"failed to create RobotCI config: {exc}") from exc

    return ScaffoldResult(
        project_root=root,
        config_path=config_path,
        replaced=replaced,
    )
