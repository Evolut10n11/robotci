from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

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


def write_result(result: ScenarioResult, path: str | Path) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(asdict(result), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output_path
