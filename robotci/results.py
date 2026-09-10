from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from robotci.metrics import NavigationMetrics

ScenarioStatus = Literal["PASS", "FAIL", "TIMEOUT", "INFRA_ERROR"]


@dataclass(frozen=True)
class Pose2D:
    x: float
    y: float
    yaw: float = 0.0


@dataclass(frozen=True)
class ScenarioResult:
    scenario: str
    status: ScenarioStatus
    duration_sec: float
    start: Pose2D
    goal: Pose2D
    navigation_result: str
    metrics: NavigationMetrics


@dataclass(frozen=True)
class SuiteScenarioResult:
    scenario: str
    status: ScenarioStatus
    duration_sec: float
    result_file: str
    metrics: NavigationMetrics | None


@dataclass(frozen=True)
class SuiteResult:
    status: ScenarioStatus
    runtime: str
    duration_sec: float
    scenarios: tuple[SuiteScenarioResult, ...]


def _write_json(payload: object, path: str | Path) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(asdict(payload), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output_path


def write_result(result: ScenarioResult, path: str | Path) -> Path:
    return _write_json(result, path)


def write_suite_result(result: SuiteResult, path: str | Path) -> Path:
    return _write_json(result, path)
