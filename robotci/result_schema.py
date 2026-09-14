from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from robotci.evidence import NavigationEvidencePolicy, evaluate_navigation_success
from robotci.metrics import NavigationMetrics, NavigationTelemetryQuality
from robotci.results import (
    RESULT_SCHEMA_VERSION,
    TASK_SCHEMA_VERSION,
    Pose2D,
    ScenarioStatus,
    ScenarioTaskIdentity,
    build_scenario_task,
)

LEGACY_RESULT_SCHEMA_VERSION = 0
PREVIOUS_RESULT_SCHEMA_VERSION = 1


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
    telemetry_quality: NavigationTelemetryQuality | None
    evidence_policy: NavigationEvidencePolicy | None
    task: ScenarioTaskIdentity | None
    provenance_complete: bool
    evidence_complete: bool
    reason_code: str | None


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


def _as_positive_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ResultSchemaError(f"{name} must be a positive integer")
    return value


def _as_bool(value: object, name: str) -> bool:
    if not isinstance(value, bool):
        raise ResultSchemaError(f"{name} must be a boolean")
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


def _parse_telemetry_quality(
    value: object,
    *,
    allow_missing: bool,
) -> NavigationTelemetryQuality | None:
    if value is None and allow_missing:
        return None
    quality = _as_mapping(value, "telemetry_quality")
    return NavigationTelemetryQuality(
        received_feedback_samples=_as_non_negative_int(
            quality.get("received_feedback_samples"),
            "telemetry_quality.received_feedback_samples",
        ),
        valid_pose_samples=_as_non_negative_int(
            quality.get("valid_pose_samples"),
            "telemetry_quality.valid_pose_samples",
        ),
        invalid_pose_samples=_as_non_negative_int(
            quality.get("invalid_pose_samples"),
            "telemetry_quality.invalid_pose_samples",
        ),
        final_pose_valid=_as_bool(
            quality.get("final_pose_valid"),
            "telemetry_quality.final_pose_valid",
        ),
    )


def _parse_evidence_policy(value: object) -> NavigationEvidencePolicy:
    policy = _as_mapping(value, "evidence_policy")
    try:
        return NavigationEvidencePolicy(
            goal_tolerance_m=_as_finite_float(
                policy.get("goal_tolerance_m"),
                "evidence_policy.goal_tolerance_m",
                non_negative=False,
            ),
            min_feedback_samples=_as_positive_int(
                policy.get("min_feedback_samples"),
                "evidence_policy.min_feedback_samples",
            ),
        )
    except ValueError as exc:
        raise ResultSchemaError(str(exc)) from exc


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
    if version not in {
        LEGACY_RESULT_SCHEMA_VERSION,
        PREVIOUS_RESULT_SCHEMA_VERSION,
        RESULT_SCHEMA_VERSION,
    }:
        raise ResultSchemaError(
            f"unsupported result.schema_version {version}; supported versions are "
            f"{LEGACY_RESULT_SCHEMA_VERSION} and {PREVIOUS_RESULT_SCHEMA_VERSION} "
            f"(read-only), and {RESULT_SCHEMA_VERSION}"
        )
    return version


def validate_result_payload(payload: object) -> ValidatedScenarioResult:
    """Validate schema v2 or adapt v0/v1 results for read-only inspection."""

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
        allow_missing=(
            source_version in {
                LEGACY_RESULT_SCHEMA_VERSION,
                PREVIOUS_RESULT_SCHEMA_VERSION,
            }
            or (source_version == RESULT_SCHEMA_VERSION and status != "PASS")
        ),
    )

    reason_code_value = result.get("reason_code")
    reason_code = (
        None
        if reason_code_value is None
        else _as_string(reason_code_value, "reason_code")
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
            telemetry_quality=None,
            evidence_policy=None,
            task=None,
            provenance_complete=False,
            evidence_complete=False,
            reason_code=reason_code,
        )

    task = _parse_task(
        result.get("task"),
        scenario=scenario,
        start=start,
        goal=goal,
    )
    if source_version == PREVIOUS_RESULT_SCHEMA_VERSION:
        return ValidatedScenarioResult(
            source_schema_version=source_version,
            scenario=scenario,
            status=status,
            duration_sec=duration_sec,
            start=start,
            goal=goal,
            navigation_result=navigation_result,
            metrics=metrics,
            telemetry_quality=None,
            evidence_policy=None,
            task=task,
            provenance_complete=task.map_id != "unspecified",
            evidence_complete=False,
            reason_code=reason_code,
        )

    evidence_policy = _parse_evidence_policy(result.get("evidence_policy"))
    telemetry_quality = _parse_telemetry_quality(
        result.get("telemetry_quality"),
        allow_missing=status != "PASS",
    )
    if (metrics is None) != (telemetry_quality is None):
        raise ResultSchemaError(
            "metrics and telemetry_quality must either both be present or both be null"
        )
    if status != "PASS" and reason_code is None:
        raise ResultSchemaError("a non-PASS result must include a non-empty reason_code")
    if metrics is None and reason_code is None:
        raise ResultSchemaError(
            "a result without metrics must include a non-empty reason_code"
        )
    if navigation_result == "SUCCEEDED":
        if metrics is None or telemetry_quality is None:
            raise ResultSchemaError(
                "a SUCCEEDED navigation result must include metrics and telemetry_quality"
            )
        decision = evaluate_navigation_success(
            metrics=metrics,
            telemetry_quality=telemetry_quality,
            policy=evidence_policy,
        )
        if status != decision.status or reason_code != decision.reason_code:
            expected = decision.reason_code or "sufficient_evidence"
            raise ResultSchemaError(
                "scenario status does not match navigation evidence: "
                f"expected {decision.status} ({expected})"
            )
    elif status == "PASS":
        raise ResultSchemaError("PASS requires navigation_result SUCCEEDED")

    return ValidatedScenarioResult(
        source_schema_version=source_version,
        scenario=scenario,
        status=status,
        duration_sec=duration_sec,
        start=start,
        goal=goal,
        navigation_result=navigation_result,
        metrics=metrics,
        telemetry_quality=telemetry_quality,
        evidence_policy=evidence_policy,
        task=task,
        provenance_complete=task.map_id != "unspecified",
        evidence_complete=True,
        reason_code=reason_code,
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
