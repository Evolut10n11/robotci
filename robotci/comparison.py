from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

from robotci.metrics import NavigationMetrics
from robotci.regression import RegressionPolicy, RegressionReport, compare_navigation_metrics


class ComparisonInputError(ValueError):
    """Raised when a persisted result cannot be used for regression comparison."""


@dataclass(frozen=True)
class ScenarioSnapshot:
    scenario: str
    duration_sec: float
    metrics: NavigationMetrics


def _as_mapping(value: object, name: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ComparisonInputError(f"{name} must be an object")
    return value


def _as_string(value: object, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ComparisonInputError(f"{name} must be a non-empty string")
    return value


def _as_non_negative_float(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ComparisonInputError(f"{name} must be a number")
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise ComparisonInputError(f"{name} must be finite and non-negative")
    return number


def _as_non_negative_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ComparisonInputError(f"{name} must be a non-negative integer")
    return value


def parse_scenario_result(payload: object) -> ScenarioSnapshot:
    """Parse the stable subset of a RobotCI scenario result needed by M4."""
    result = _as_mapping(payload, "result")
    scenario = _as_string(result.get("scenario"), "scenario")
    status = _as_string(result.get("status"), "status")
    if status != "PASS":
        raise ComparisonInputError(
            f"scenario '{scenario}' must have PASS status before metrics can be compared"
        )

    duration_sec = _as_non_negative_float(result.get("duration_sec"), "duration_sec")
    metrics_payload = _as_mapping(result.get("metrics"), "metrics")
    metrics = NavigationMetrics(
        path_length_m=_as_non_negative_float(
            metrics_payload.get("path_length_m"), "metrics.path_length_m"
        ),
        distance_to_goal_m=_as_non_negative_float(
            metrics_payload.get("distance_to_goal_m"), "metrics.distance_to_goal_m"
        ),
        stuck_events=_as_non_negative_int(
            metrics_payload.get("stuck_events"), "metrics.stuck_events"
        ),
        feedback_samples=_as_non_negative_int(
            metrics_payload.get("feedback_samples"), "metrics.feedback_samples"
        ),
        recoveries=_as_non_negative_int(
            metrics_payload.get("recoveries"), "metrics.recoveries"
        ),
    )
    return ScenarioSnapshot(
        scenario=scenario,
        duration_sec=duration_sec,
        metrics=metrics,
    )


def load_scenario_result(path: str | Path) -> ScenarioSnapshot:
    result_path = Path(path)
    try:
        payload = json.loads(result_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ComparisonInputError(f"cannot read result file '{result_path}': {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ComparisonInputError(f"invalid JSON in result file '{result_path}': {exc}") from exc
    return parse_scenario_result(payload)


def compare_scenario_results(
    *,
    baseline: ScenarioSnapshot,
    candidate: ScenarioSnapshot,
    policy: RegressionPolicy | None = None,
) -> RegressionReport:
    if baseline.scenario != candidate.scenario:
        raise ComparisonInputError(
            "baseline and candidate must describe the same scenario "
            f"('{baseline.scenario}' != '{candidate.scenario}')"
        )

    return compare_navigation_metrics(
        baseline_duration_sec=baseline.duration_sec,
        baseline=baseline.metrics,
        candidate_duration_sec=candidate.duration_sec,
        candidate=candidate.metrics,
        policy=policy,
    )


def compare_scenario_result_files(
    *,
    baseline_path: str | Path,
    candidate_path: str | Path,
    policy: RegressionPolicy | None = None,
) -> RegressionReport:
    return compare_scenario_results(
        baseline=load_scenario_result(baseline_path),
        candidate=load_scenario_result(candidate_path),
        policy=policy,
    )
