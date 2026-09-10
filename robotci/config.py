from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml

RuntimeName = Literal["auto", "native", "docker"]


class ConfigError(ValueError):
    """Raised when robotci.yaml is missing or invalid."""


@dataclass(frozen=True)
class PoseConfig:
    x: float
    y: float
    yaw: float = 0.0


@dataclass(frozen=True)
class ScenarioConfig:
    name: str
    start: PoseConfig
    goal: PoseConfig
    timeout_sec: float


@dataclass(frozen=True)
class RobotCIConfig:
    version: int
    runtime: RuntimeName
    scenarios: tuple[ScenarioConfig, ...]


def _require_mapping(value: object, name: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ConfigError(f"{name} must be a mapping")
    return value


def _require_number(value: object, name: str) -> float:
    if not isinstance(value, int | float):
        raise ConfigError(f"{name} must be a number")
    return float(value)


def _parse_pose(value: object, name: str) -> PoseConfig:
    data = _require_mapping(value, name)

    if "x" not in data:
        raise ConfigError(f"{name}.x is required")
    if "y" not in data:
        raise ConfigError(f"{name}.y is required")

    x = _require_number(data["x"], f"{name}.x")
    y = _require_number(data["y"], f"{name}.y")
    yaw = _require_number(data.get("yaw", 0.0), f"{name}.yaw")

    return PoseConfig(
        x=x,
        y=y,
        yaw=yaw,
    )


def _parse_scenario(value: object, index: int) -> ScenarioConfig:
    prefix = f"scenarios[{index}]"
    data = _require_mapping(value, prefix)

    name = data.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ConfigError(f"{prefix}.name must be a non-empty string")

    if "start" not in data:
        raise ConfigError(f"{prefix}.start is required")

    if "goal" not in data:
        raise ConfigError(f"{prefix}.goal is required")

    start = _parse_pose(data["start"], f"{prefix}.start")
    goal = _parse_pose(data["goal"], f"{prefix}.goal")

    timeout_sec = _require_number(
        data.get("timeout_sec", 120.0),
        f"{prefix}.timeout_sec",
    )

    if timeout_sec <= 0:
        raise ConfigError(f"{prefix}.timeout_sec must be greater than zero")

    return ScenarioConfig(
        name=name,
        start=start,
        goal=goal,
        timeout_sec=timeout_sec,
    )


def load_config(path: str | Path = "robotci.yaml") -> RobotCIConfig:
    config_path = Path(path)

    if not config_path.is_file():
        raise ConfigError(f"RobotCI config not found: {config_path}")

    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"Invalid YAML in {config_path}: {exc}") from exc
    except OSError as exc:
        raise ConfigError(f"Failed to read {config_path}: {exc}") from exc

    data = _require_mapping(raw, "config")

    version = data.get("version")
    if version != 1:
        raise ConfigError("config.version must be 1")

    runtime = data.get("runtime", "auto")
    if runtime not in {"auto", "native", "docker"}:
        raise ConfigError(
            "config.runtime must be one of: auto, native, docker"
        )

    raw_scenarios = data.get("scenarios")
    if not isinstance(raw_scenarios, list):
        raise ConfigError("config.scenarios must be a list")

    if not raw_scenarios:
        raise ConfigError("config.scenarios must contain at least one scenario")

    scenarios = tuple(
        _parse_scenario(value, index)
        for index, value in enumerate(raw_scenarios)
    )

    names = [scenario.name for scenario in scenarios]

    if len(names) != len(set(names)):
        raise ConfigError("scenario names must be unique")

    return RobotCIConfig(
        version=1,
        runtime=runtime,  # type: ignore[arg-type]
        scenarios=scenarios,
    )