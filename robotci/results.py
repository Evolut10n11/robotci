from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path
from typing import Literal

from robotci.evidence import NavigationEvidencePolicy
from robotci.metrics import NavigationMetrics, NavigationTelemetryQuality

ScenarioStatus = Literal["PASS", "FAIL", "TIMEOUT", "INFRA_ERROR"]
RESULT_SCHEMA_VERSION = 2
TASK_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class Pose2D:
    x: float
    y: float
    yaw: float = 0.0


@dataclass(frozen=True)
class ScenarioTaskIdentity:
    schema_version: int
    frame_id: str
    map_id: str
    fingerprint: str


def build_scenario_task(
    *,
    scenario: str,
    start: Pose2D,
    goal: Pose2D,
    map_id: str,
    frame_id: str = "map",
) -> ScenarioTaskIdentity:
    """Build a stable identity for the navigation task, excluding implementation changes."""

    if not scenario or not frame_id or not map_id:
        raise ValueError("scenario, frame_id and map_id must be non-empty")

    def canonical_pose(pose: Pose2D) -> dict[str, float]:
        values = (pose.x, pose.y, pose.yaw)
        if any(isinstance(value, bool) or not math.isfinite(float(value)) for value in values):
            raise ValueError("task poses must contain finite numbers")
        return {
            name: 0.0 if float(value) == 0 else float(value)
            for name, value in zip(("x", "y", "yaw"), values, strict=True)
        }

    definition = {
        "schema_version": TASK_SCHEMA_VERSION,
        "scenario": scenario,
        "frame_id": frame_id,
        "map_id": map_id,
        "start": canonical_pose(start),
        "goal": canonical_pose(goal),
    }
    canonical = json.dumps(
        definition,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return ScenarioTaskIdentity(
        schema_version=TASK_SCHEMA_VERSION,
        frame_id=frame_id,
        map_id=map_id,
        fingerprint=f"sha256:{sha256(canonical).hexdigest()}",
    )


@dataclass(frozen=True)
class ScenarioResult:
    scenario: str
    status: ScenarioStatus
    duration_sec: float
    start: Pose2D
    goal: Pose2D
    navigation_result: str
    metrics: NavigationMetrics
    telemetry_quality: NavigationTelemetryQuality
    evidence_policy: NavigationEvidencePolicy
    task: ScenarioTaskIdentity
    reason_code: str | None = None
    schema_version: int = RESULT_SCHEMA_VERSION


@dataclass(frozen=True)
class SuiteScenarioResult:
    scenario: str
    status: ScenarioStatus
    duration_sec: float
    result_file: str


@dataclass(frozen=True)
class SuiteResult:
    status: ScenarioStatus
    runtime: str
    duration_sec: float
    scenarios: tuple[SuiteScenarioResult, ...]


def _write_json(payload: dict[str, object], path: str | Path) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, allow_nan=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output_path


def write_result(result: ScenarioResult, path: str | Path) -> Path:
    payload = asdict(result)
    if payload["reason_code"] is None:
        del payload["reason_code"]
    # Imported lazily because the reader owns validation and imports these types.
    from robotci.result_schema import validate_result_payload

    validate_result_payload(payload)
    return _write_json(payload, path)


def write_suite_result(result: SuiteResult, path: str | Path) -> Path:
    return _write_json(asdict(result), path)
