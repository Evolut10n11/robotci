from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

from robotci.config import ConfigError, PoseConfig, RuntimeName, get_scenario, load_config
from robotci.runner import _find_project_root, _resolve_config_path


@dataclass(frozen=True)
class PlannedScenario:
    name: str
    start: PoseConfig
    goal: PoseConfig
    timeout_sec: float

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "start": {
                "x": self.start.x,
                "y": self.start.y,
                "yaw": self.start.yaw,
            },
            "goal": {
                "x": self.goal.x,
                "y": self.goal.y,
                "yaw": self.goal.yaw,
            },
            "timeout_sec": self.timeout_sec,
        }


@dataclass(frozen=True)
class ExecutionPlan:
    runtime: RuntimeName
    scenarios: tuple[PlannedScenario, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "runtime": self.runtime,
            "scenarios": [scenario.as_dict() for scenario in self.scenarios],
        }


def build_execution_plan(
    *,
    config_path: str | Path = "robotci.yaml",
    scenario: str | None = None,
    runtime: RuntimeName | None = None,
    timeout_sec: float | None = None,
    project_root: Path | None = None,
) -> ExecutionPlan:
    """Resolve config and CLI overrides without probing or starting a runtime."""
    if timeout_sec is not None and (
        not math.isfinite(timeout_sec) or timeout_sec <= 0
    ):
        raise ConfigError("timeout must be a finite number greater than zero")

    root = _find_project_root(project_root)
    resolved_config = _resolve_config_path(root, config_path)
    config = load_config(resolved_config)
    definitions = (
        (get_scenario(config, scenario),)
        if scenario is not None
        else config.scenarios
    )
    selected_runtime = runtime or config.runtime

    planned = tuple(
        PlannedScenario(
            name=definition.name,
            start=definition.start,
            goal=definition.goal,
            timeout_sec=(
                definition.timeout_sec if timeout_sec is None else timeout_sec
            ),
        )
        for definition in definitions
    )

    return ExecutionPlan(runtime=selected_runtime, scenarios=planned)
