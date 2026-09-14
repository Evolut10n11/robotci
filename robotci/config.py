from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

import yaml

RuntimeName = Literal["auto", "native", "docker"]
_SCENARIO_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


class ConfigError(ValueError):
    """Raised when robotci.yaml is missing or invalid."""


class _UniqueKeyLoader(yaml.SafeLoader):
    """Safe YAML loader that rejects duplicate mapping keys."""


def _construct_unique_mapping(
    loader: _UniqueKeyLoader,
    node: yaml.MappingNode,
    deep: bool = False,
) -> dict[object, object]:
    seen: dict[object, yaml.Node] = {}
    merge_key = object()
    for key_node, _value_node in node.value:
        is_merge = key_node.tag == "tag:yaml.org,2002:merge"
        key = merge_key if is_merge else loader.construct_object(key_node, deep=False)
        try:
            duplicate = key in seen
        except TypeError as exc:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                "found an unhashable mapping key",
                key_node.start_mark,
            ) from exc
        if duplicate:
            display_key = "<<" if is_merge else repr(key)
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"found duplicate key {display_key}",
                key_node.start_mark,
            )
        seen[key] = key_node

    loader.flatten_mapping(node)
    return yaml.constructor.SafeConstructor.construct_mapping(
        loader,
        node,
        deep=deep,
    )


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


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
    map_id: str | None = None
    goal_tolerance_m: float = 0.25
    min_feedback_samples: int = 1


@dataclass(frozen=True)
class RobotCIConfig:
    version: int
    runtime: RuntimeName
    scenarios: tuple[ScenarioConfig, ...]


def _require_mapping(value: object, name: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ConfigError(f"{name} must be a mapping")
    return value


def _reject_unknown_keys(
    data: dict[str, object],
    *,
    allowed: set[str],
    name: str,
) -> None:
    unknown = sorted(repr(key) for key in data if key not in allowed)
    if unknown:
        raise ConfigError(f"{name} contains unknown keys: {', '.join(unknown)}")


def _require_number(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ConfigError(f"{name} must be a number")
    try:
        number = float(value)
    except OverflowError as exc:
        raise ConfigError(f"{name} must be finite") from exc
    if not math.isfinite(number):
        raise ConfigError(f"{name} must be finite")
    return number


def _parse_pose(value: object, name: str) -> PoseConfig:
    data = _require_mapping(value, name)
    _reject_unknown_keys(data, allowed={"x", "y", "yaw"}, name=name)

    if "x" not in data:
        raise ConfigError(f"{name}.x is required")
    if "y" not in data:
        raise ConfigError(f"{name}.y is required")

    return PoseConfig(
        x=_require_number(data["x"], f"{name}.x"),
        y=_require_number(data["y"], f"{name}.y"),
        yaw=_require_number(data.get("yaw", 0.0), f"{name}.yaw"),
    )


def _parse_scenario(value: object, index: int) -> ScenarioConfig:
    prefix = f"scenarios[{index}]"
    data = _require_mapping(value, prefix)
    _reject_unknown_keys(
        data,
        allowed={
            "name",
            "map_id",
            "start",
            "goal",
            "timeout_sec",
            "goal_tolerance_m",
            "min_feedback_samples",
        },
        name=prefix,
    )

    name = data.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ConfigError(f"{prefix}.name must be a non-empty string")

    clean_name = name.strip()
    if not _SCENARIO_NAME_RE.fullmatch(clean_name):
        raise ConfigError(
            f"{prefix}.name must use only letters, numbers, '_' or '-'"
        )

    if "start" not in data:
        raise ConfigError(f"{prefix}.start is required")
    if "goal" not in data:
        raise ConfigError(f"{prefix}.goal is required")

    timeout_sec = _require_number(
        data.get("timeout_sec", 120.0),
        f"{prefix}.timeout_sec",
    )
    if timeout_sec <= 0:
        raise ConfigError(f"{prefix}.timeout_sec must be greater than zero")

    goal_tolerance_m = _require_number(
        data.get("goal_tolerance_m", 0.25),
        f"{prefix}.goal_tolerance_m",
    )
    if goal_tolerance_m <= 0:
        raise ConfigError(f"{prefix}.goal_tolerance_m must be greater than zero")

    min_feedback_samples = data.get("min_feedback_samples", 1)
    if (
        isinstance(min_feedback_samples, bool)
        or not isinstance(min_feedback_samples, int)
        or min_feedback_samples <= 0
    ):
        raise ConfigError(f"{prefix}.min_feedback_samples must be a positive integer")

    map_id = data.get("map_id")
    if map_id is not None:
        if not isinstance(map_id, str) or not map_id.strip():
            raise ConfigError(f"{prefix}.map_id must be a non-empty string")
        map_id = map_id.strip()
        if len(map_id) > 256:
            raise ConfigError(f"{prefix}.map_id must be at most 256 characters")

    return ScenarioConfig(
        name=clean_name,
        start=_parse_pose(data["start"], f"{prefix}.start"),
        goal=_parse_pose(data["goal"], f"{prefix}.goal"),
        timeout_sec=timeout_sec,
        map_id=map_id,
        goal_tolerance_m=goal_tolerance_m,
        min_feedback_samples=min_feedback_samples,
    )


def load_config(path: str | Path = "robotci.yaml") -> RobotCIConfig:
    config_path = Path(path)

    if not config_path.is_file():
        raise ConfigError(f"RobotCI config not found: {config_path}")

    try:
        raw = yaml.load(  # The custom loader inherits yaml.SafeLoader.
            config_path.read_text(encoding="utf-8-sig"),
            Loader=_UniqueKeyLoader,
        )
    except yaml.YAMLError as exc:
        raise ConfigError(f"Invalid YAML in {config_path}: {exc}") from exc
    except OSError as exc:
        raise ConfigError(f"Failed to read {config_path}: {exc}") from exc

    data = _require_mapping(raw, "config")
    _reject_unknown_keys(
        data,
        allowed={"version", "runtime", "scenarios"},
        name="config",
    )

    version = data.get("version")
    if isinstance(version, bool) or not isinstance(version, int) or version != 1:
        raise ConfigError("config.version must be 1")

    runtime = data.get("runtime", "auto")
    if not isinstance(runtime, str) or runtime not in {"auto", "native", "docker"}:
        raise ConfigError("config.runtime must be one of: auto, native, docker")

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
        runtime=cast(RuntimeName, runtime),
        scenarios=scenarios,
    )


def get_scenario(config: RobotCIConfig, name: str) -> ScenarioConfig:
    for scenario in config.scenarios:
        if scenario.name == name:
            return scenario

    supported = ", ".join(scenario.name for scenario in config.scenarios)
    raise ConfigError(f"unknown scenario '{name}'; configured: {supported}")
