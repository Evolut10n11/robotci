from __future__ import annotations

from dataclasses import dataclass

from robotci.results import Pose2D


@dataclass(frozen=True)
class ScenarioDefinition:
    name: str
    start: Pose2D
    goal: Pose2D


_SCENARIOS = {
    "short_route": ScenarioDefinition(
        name="short_route",
        start=Pose2D(x=0.0, y=0.0, yaw=0.0),
        goal=Pose2D(x=4.0, y=-0.17, yaw=0.0),
    ),
    "medium_route": ScenarioDefinition(
        name="medium_route",
        start=Pose2D(x=0.0, y=0.0, yaw=0.0),
        goal=Pose2D(x=9.0, y=-0.39, yaw=0.0),
    ),
    "simple_route": ScenarioDefinition(
        name="simple_route",
        start=Pose2D(x=0.0, y=0.0, yaw=0.0),
        goal=Pose2D(x=17.86, y=-0.77, yaw=0.0),
    ),
}


def scenario_names() -> tuple[str, ...]:
    return tuple(_SCENARIOS)


def get_scenario(name: str) -> ScenarioDefinition:
    try:
        return _SCENARIOS[name]
    except KeyError as exc:
        supported = ", ".join(scenario_names())
        raise ValueError(f"unsupported scenario '{name}'; supported: {supported}") from exc
