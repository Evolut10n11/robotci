from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

from robotci.metrics import NavigationMetrics

RegressionStatus = Literal["PASS", "REGRESSION"]


@dataclass(frozen=True)
class RegressionPolicy:
    """Allowed degradation before a candidate is treated as a regression."""

    max_duration_increase_pct: float = 10.0
    max_path_length_increase_pct: float = 10.0
    max_distance_to_goal_increase_m: float = 0.1
    max_stuck_events_increase: int = 0
    max_recoveries_increase: int = 0

    def __post_init__(self) -> None:
        numeric_limits = (
            self.max_duration_increase_pct,
            self.max_path_length_increase_pct,
            self.max_distance_to_goal_increase_m,
        )
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or value < 0
            for value in numeric_limits
        ):
            raise ValueError("numeric regression limits must be finite and non-negative")

        count_limits = (
            self.max_stuck_events_increase,
            self.max_recoveries_increase,
        )
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value < 0
            for value in count_limits
        ):
            raise ValueError("count regression limits must be non-negative integers")


@dataclass(frozen=True)
class RegressionFinding:
    metric: str
    baseline: float
    candidate: float
    increase: float
    allowed_increase: float
    unit: Literal["percent", "m", "count"]


@dataclass(frozen=True)
class RegressionReport:
    status: RegressionStatus
    findings: tuple[RegressionFinding, ...]


def _percent_increase(*, baseline: float, candidate: float) -> float:
    values = (baseline, candidate)
    if any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        for value in values
    ):
        raise ValueError("regression metrics must be finite numbers")
    if baseline < 0 or candidate < 0:
        raise ValueError("regression metrics must be non-negative")
    if baseline == 0:
        return 0.0 if candidate == 0 else math.inf
    return ((candidate - baseline) / baseline) * 100.0


def _exceeds_limit(increase: float, limit: float) -> bool:
    """Treat mathematically equal threshold values as inclusive despite float noise."""
    return increase > limit and not math.isclose(
        increase,
        limit,
        rel_tol=1e-9,
        abs_tol=1e-12,
    )


def _validate_navigation_metrics(label: str, metrics: NavigationMetrics) -> None:
    numeric_metrics = (
        ("path_length_m", metrics.path_length_m),
        ("distance_to_goal_m", metrics.distance_to_goal_m),
    )
    for name, value in numeric_metrics:
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or value < 0
        ):
            raise ValueError(f"{label}.{name} must be finite and non-negative")

    count_metrics = (
        ("stuck_events", metrics.stuck_events),
        ("feedback_samples", metrics.feedback_samples),
        ("recoveries", metrics.recoveries),
    )
    for name, value in count_metrics:
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"{label}.{name} must be a non-negative integer")


def compare_navigation_metrics(
    *,
    baseline_duration_sec: float,
    baseline: NavigationMetrics,
    candidate_duration_sec: float,
    candidate: NavigationMetrics,
    policy: RegressionPolicy | None = None,
) -> RegressionReport:
    """Compare one successful candidate scenario with a successful baseline."""
    selected_policy = policy or RegressionPolicy()
    _validate_navigation_metrics("baseline", baseline)
    _validate_navigation_metrics("candidate", candidate)
    findings: list[RegressionFinding] = []

    duration_increase = _percent_increase(
        baseline=baseline_duration_sec,
        candidate=candidate_duration_sec,
    )
    if _exceeds_limit(
        duration_increase,
        selected_policy.max_duration_increase_pct,
    ):
        findings.append(
            RegressionFinding(
                metric="duration_sec",
                baseline=baseline_duration_sec,
                candidate=candidate_duration_sec,
                increase=duration_increase,
                allowed_increase=selected_policy.max_duration_increase_pct,
                unit="percent",
            )
        )

    path_increase = _percent_increase(
        baseline=baseline.path_length_m,
        candidate=candidate.path_length_m,
    )
    if _exceeds_limit(
        path_increase,
        selected_policy.max_path_length_increase_pct,
    ):
        findings.append(
            RegressionFinding(
                metric="path_length_m",
                baseline=baseline.path_length_m,
                candidate=candidate.path_length_m,
                increase=path_increase,
                allowed_increase=selected_policy.max_path_length_increase_pct,
                unit="percent",
            )
        )

    distance_increase = candidate.distance_to_goal_m - baseline.distance_to_goal_m
    if _exceeds_limit(
        distance_increase,
        selected_policy.max_distance_to_goal_increase_m,
    ):
        findings.append(
            RegressionFinding(
                metric="distance_to_goal_m",
                baseline=baseline.distance_to_goal_m,
                candidate=candidate.distance_to_goal_m,
                increase=distance_increase,
                allowed_increase=selected_policy.max_distance_to_goal_increase_m,
                unit="m",
            )
        )

    stuck_increase = candidate.stuck_events - baseline.stuck_events
    if stuck_increase > selected_policy.max_stuck_events_increase:
        findings.append(
            RegressionFinding(
                metric="stuck_events",
                baseline=float(baseline.stuck_events),
                candidate=float(candidate.stuck_events),
                increase=float(stuck_increase),
                allowed_increase=float(selected_policy.max_stuck_events_increase),
                unit="count",
            )
        )

    recoveries_increase = candidate.recoveries - baseline.recoveries
    if recoveries_increase > selected_policy.max_recoveries_increase:
        findings.append(
            RegressionFinding(
                metric="recoveries",
                baseline=float(baseline.recoveries),
                candidate=float(candidate.recoveries),
                increase=float(recoveries_increase),
                allowed_increase=float(selected_policy.max_recoveries_increase),
                unit="count",
            )
        )

    status: RegressionStatus = "REGRESSION" if findings else "PASS"
    return RegressionReport(status=status, findings=tuple(findings))
