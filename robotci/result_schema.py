from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from robotci.metrics import NavigationMetrics
from robotci.results import (
    RESULT_SCHEMA_VERSION,
    TASK_SCHEMA_VERSION,
    Pose2D,
    ScenarioStatus,
    ScenarioTaskIdentity,
    build_scenario_task,
)

LEGACY_RESULT_SCHEMA_VERSION = 0


class ResultSchemaError(ValueError):
    """Raised when a scenario result does not satisfy a supported schema."""


def _strict_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ResultSchemaError(f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> object:
    raise ResultSchemaError(f"invalid non-finite JSON number: {value}")


@dataclass(frozen=True)
class ValidatedScenarioResult:
    source_schema_version: int
    scenario: str
    status: ScenarioStatus
    duration_sec: float
    start: Pose2D
    goal: Pose2D
    navigation_result: str
    metrics: NavigationMetrics | None
    task: ScenarioTaskIdentity | None
    provenance_complete: bool


def _as_mapping(value: object, name: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ResultSchemaError(f"{name} must be an object")
    return value


def _as_string(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ResultSchemaError(f"{name} must be a non-empty string")
    if value != value.strip():
        raise ResultSchemaError(f"{name} must not have surrounding whitespace")
    return value


def _as_finite_float(value: object, name: str, *, non_negative: bool) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ResultSchemaError(f"{name} must be a number")
    try:
        number = float(value)
    except OverflowError as exc:
        raise ResultSchemaError(f"{name} must be finite") from exc
    if not math.isfinite(number):
        raise ResultSchemaError(f"{name} must be finite")
    if non_negative and number < 0:
        raise ResultSchemaError(f"{name} must be non-negative")
    return number


def _as_non_negative_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ResultSchemaError(f"{name} must be a non-negative integer")
    return value


def _parse_pose(value: object, name: str) -> Pose2D:
    pose = _as_mapping(value, name)
    return Pose2D(
        x=_as_finite_float(pose.get("x"), f"{name}.x", non_negative=False),
        y=_as_finite_float(pose.get("y"), f"{name}.y", non_negative=False),
        yaw=_as_finite_float(pose.get("yaw"), f"{name}.yaw", non_negative=False),
    )


def _parse_metrics(value: object, *, allow_missing: bool) -> NavigationMetrics | None:
    if value is None and allow_missing:
        return None
    metrics = _as_mapping(value, "metrics")
    return NavigationMetrics(
        path_length_m=_as_finite_float(
            metrics.get("path_length_m"),
            "metrics.path_length_m",
            non_negative=True,
        ),
        distance_to_goal_m=_as_finite_float(
            metrics.get("distance_to_goal_m"),
            "metrics.distance_to_goal_m",
            non_negative=True,
        ),
        stuck_events=_as_non_negative_int(
            metrics.get("stuck_events"),
            "metrics.stuck_events",
        ),
        feedback_samples=_as_non_negative_int(
            metrics.get("feedback_samples"),
            "metrics.feedback_samples",
        ),
        recoveries=_as_non_negative_int(
            metrics.get("recoveries"),
            "metrics.recoveries",
        ),
    )


def _parse_task(
    value: object,
    *,
    scenario: str,
    start: Pose2D,
    goal: Pose2D,
) -> ScenarioTaskIdentity:
    task = _as_mapping(value, "task")
    schema_version = task.get("schema_version")
    if (
        not isinstance(schema_version, int)
        or isinstance(schema_version, bool)
        or schema_version != TASK_SCHEMA_VERSION
    ):
        raise ResultSchemaError(
            f"task.schema_version must be {TASK_SCHEMA_VERSION}"
        )
    frame_id = _as_string(task.get("frame_id"), "task.frame_id")
    map_id = _as_string(task.get("map_id"), "task.map_id")
    fingerprint = _as_string(task.get("fingerprint"), "task.fingerprint")
    expected = build_scenario_task(
        scenario=scenario,
        start=start,
        goal=goal,
        map_id=map_id,
        frame_id=frame_id,
    )
    if fingerprint != expected.fingerprint:
        raise ResultSchemaError(
            "task.fingerprint does not match scenario, start, goal, frame and map"
        )
    return expected


def _result_version(result: dict[str, object]) -> int:
    if "schema_version" not in result:
        return LEGACY_RESULT_SCHEMA_VERSION
    version = result["schema_version"]
    if not isinstance(version, int) or isinstance(version, bool):
        raise ResultSchemaError("result.schema_version must be an integer")
    if version not in {LEGACY_RESULT_SCHEMA_VERSION, RESULT_SCHEMA_VERSION}:
        raise ResultSchemaError(
            f"unsupported result.schema_version {version}; supported versions are "
            f"{LEGACY_RESULT_SCHEMA_VERSION} (legacy read-only) and "
            f"{RESULT_SCHEMA_VERSION}"
        )
    return version


def validate_result_payload(payload: object) -> ValidatedScenarioResult:
    """Validate a current result or adapt a legacy v0 result for read-only use."""

    result = _as_mapping(payload, "result")
    source_version = _result_version(result)
    scenario = _as_string(result.get("scenario"), "scenario")
    status_value = _as_string(result.get("status"), "status")
    if status_value not in {"PASS", "FAIL", "TIMEOUT", "INFRA_ERROR"}:
        raise ResultSchemaError(f"unsupported scenario status: {status_value}")
    status = cast(ScenarioStatus, status_value)
    duration_sec = _as_finite_float(
        result.get("duration_sec"),
        "duration_sec",
        non_negative=True,
    )
    start = _parse_pose(result.get("start"), "start")
    goal = _parse_pose(result.get("goal"), "goal")
    navigation_result = _as_string(
        result.get("navigation_result"),
        "navigation_result",
    )
    metrics = _parse_metrics(
        result.get("metrics"),
        allow_missing=source_version == RESULT_SCHEMA_VERSION and status != "PASS",
    )

    if source_version == LEGACY_RESULT_SCHEMA_VERSION:
        if "task" in result:
            raise ResultSchemaError(
                "legacy result v0 must not contain task identity without schema_version"
            )
        return ValidatedScenarioResult(
            source_schema_version=source_version,
            scenario=scenario,
            status=status,
            duration_sec=duration_sec,
            start=start,
            goal=goal,
            navigation_result=navigation_result,
            metrics=metrics,
            task=None,
            provenance_complete=False,
        )

    task = _parse_task(
        result.get("task"),
        scenario=scenario,
        start=start,
        goal=goal,
    )
    reason_code = result.get("reason_code")
    if reason_code is not None:
        _as_string(reason_code, "reason_code")
    if metrics is None and reason_code is None:
        raise ResultSchemaError(
            "a result without metrics must include a non-empty reason_code"
        )
    return ValidatedScenarioResult(
        source_schema_version=source_version,
        scenario=scenario,
        status=status,
        duration_sec=duration_sec,
        start=start,
        goal=goal,
        navigation_result=navigation_result,
        metrics=metrics,
        task=task,
        provenance_complete=task.map_id != "unspecified",
    )


def load_result(path: str | Path) -> ValidatedScenarioResult:
    result_path = Path(path)
    try:
        payload = json.loads(
            result_path.read_text(encoding="utf-8"),
            object_pairs_hook=_strict_json_object,
            parse_constant=_reject_json_constant,
        )
    except OSError as exc:
        raise ResultSchemaError(f"cannot read result file '{result_path}': {exc}") from exc
    except UnicodeError as exc:
        raise ResultSchemaError(
            f"result file is not valid UTF-8 '{result_path}': {exc}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise ResultSchemaError(
            f"invalid JSON in result file '{result_path}': {exc}"
        ) from exc
    return validate_result_payload(payload)
