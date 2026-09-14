from __future__ import annotations

import math

import pytest

from robotci.metrics import NavigationMetrics
from robotci.regression import RegressionPolicy, compare_navigation_metrics


def _metrics(
    *,
    path_length_m: float = 10.0,
    distance_to_goal_m: float = 0.05,
    stuck_events: int = 0,
    recoveries: int = 0,
) -> NavigationMetrics:
    return NavigationMetrics(
        path_length_m=path_length_m,
        distance_to_goal_m=distance_to_goal_m,
        stuck_events=stuck_events,
        feedback_samples=10,
        recoveries=recoveries,
    )


def test_regression_report_passes_within_policy() -> None:
    report = compare_navigation_metrics(
        baseline_duration_sec=100.0,
        baseline=_metrics(path_length_m=10.0),
        candidate_duration_sec=109.0,
        candidate=_metrics(path_length_m=10.9),
    )

    assert report.status == "PASS"
    assert report.findings == ()


def test_regression_report_flags_duration_and_path_degradation() -> None:
    report = compare_navigation_metrics(
        baseline_duration_sec=100.0,
        baseline=_metrics(path_length_m=10.0),
        candidate_duration_sec=125.0,
        candidate=_metrics(path_length_m=12.0),
    )

    assert report.status == "REGRESSION"
    assert [finding.metric for finding in report.findings] == [
        "duration_sec",
        "path_length_m",
    ]
    assert report.findings[0].increase == 25.0
    assert report.findings[1].increase == 20.0


def test_regression_report_flags_distance_to_goal_degradation() -> None:
    report = compare_navigation_metrics(
        baseline_duration_sec=10.0,
        baseline=_metrics(distance_to_goal_m=0.05),
        candidate_duration_sec=10.0,
        candidate=_metrics(distance_to_goal_m=0.16),
    )

    assert report.status == "REGRESSION"
    assert len(report.findings) == 1
    finding = report.findings[0]
    assert finding.metric == "distance_to_goal_m"
    assert finding.increase == pytest.approx(0.11)
    assert finding.allowed_increase == 0.1
    assert finding.unit == "m"


def test_distance_threshold_is_inclusive_despite_float_noise() -> None:
    report = compare_navigation_metrics(
        baseline_duration_sec=10.0,
        baseline=_metrics(distance_to_goal_m=0.05),
        candidate_duration_sec=10.0,
        candidate=_metrics(distance_to_goal_m=0.15),
    )

    assert report.status == "PASS"


def test_regression_report_flags_new_stuck_events_and_recoveries() -> None:
    report = compare_navigation_metrics(
        baseline_duration_sec=10.0,
        baseline=_metrics(stuck_events=1, recoveries=1),
        candidate_duration_sec=10.0,
        candidate=_metrics(stuck_events=2, recoveries=3),
        policy=RegressionPolicy(
            max_stuck_events_increase=0,
            max_recoveries_increase=1,
        ),
    )

    assert report.status == "REGRESSION"
    assert [finding.metric for finding in report.findings] == [
        "stuck_events",
        "recoveries",
    ]


def test_regression_threshold_is_inclusive() -> None:
    report = compare_navigation_metrics(
        baseline_duration_sec=100.0,
        baseline=_metrics(path_length_m=10.0),
        candidate_duration_sec=110.0,
        candidate=_metrics(path_length_m=11.0),
    )

    assert report.status == "PASS"


def test_decimal_threshold_is_inclusive_despite_float_noise() -> None:
    report = compare_navigation_metrics(
        baseline_duration_sec=0.3,
        baseline=_metrics(path_length_m=0.3),
        candidate_duration_sec=0.33,
        candidate=_metrics(path_length_m=0.33),
    )

    assert report.status == "PASS"
    assert report.findings == ()


def test_zero_baseline_only_regresses_when_candidate_is_nonzero() -> None:
    stable = compare_navigation_metrics(
        baseline_duration_sec=0.0,
        baseline=_metrics(path_length_m=0.0),
        candidate_duration_sec=0.0,
        candidate=_metrics(path_length_m=0.0),
    )
    degraded = compare_navigation_metrics(
        baseline_duration_sec=0.0,
        baseline=_metrics(path_length_m=0.0),
        candidate_duration_sec=1.0,
        candidate=_metrics(path_length_m=1.0),
    )

    assert stable.status == "PASS"
    assert degraded.status == "REGRESSION"
    assert math.isinf(degraded.findings[0].increase)


@pytest.mark.parametrize(
    "policy",
    [
        RegressionPolicy(max_stuck_events_increase=0),
        RegressionPolicy(max_recoveries_increase=0),
    ],
)
def test_valid_zero_count_limits(policy: RegressionPolicy) -> None:
    assert policy.max_stuck_events_increase >= 0
    assert policy.max_recoveries_increase >= 0


def test_policy_rejects_invalid_limits() -> None:
    with pytest.raises(ValueError):
        RegressionPolicy(max_duration_increase_pct=-1.0)
    with pytest.raises(ValueError):
        RegressionPolicy(max_path_length_increase_pct=math.inf)
    with pytest.raises(ValueError):
        RegressionPolicy(max_distance_to_goal_increase_m=math.nan)
    with pytest.raises(ValueError):
        RegressionPolicy(max_stuck_events_increase=-1)
    with pytest.raises(ValueError):
        RegressionPolicy(max_recoveries_increase=0.5)  # type: ignore[arg-type]


def test_comparison_rejects_non_finite_or_negative_metrics() -> None:
    with pytest.raises(ValueError):
        compare_navigation_metrics(
            baseline_duration_sec=10.0,
            baseline=_metrics(),
            candidate_duration_sec=math.nan,
            candidate=_metrics(),
        )
    with pytest.raises(ValueError):
        compare_navigation_metrics(
            baseline_duration_sec=10.0,
            baseline=_metrics(path_length_m=-1.0),
            candidate_duration_sec=10.0,
            candidate=_metrics(),
        )
    with pytest.raises(ValueError, match="candidate.distance_to_goal_m"):
        compare_navigation_metrics(
            baseline_duration_sec=10.0,
            baseline=_metrics(),
            candidate_duration_sec=10.0,
            candidate=_metrics(distance_to_goal_m=math.inf),
        )
    with pytest.raises(ValueError, match="candidate.recoveries"):
        compare_navigation_metrics(
            baseline_duration_sec=10.0,
            baseline=_metrics(),
            candidate_duration_sec=10.0,
            candidate=_metrics(recoveries=-1),
        )
