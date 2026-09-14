from __future__ import annotations

import pytest

from robotci.evidence import NavigationEvidencePolicy, evaluate_navigation_success
from robotci.metrics import NavigationMetrics, NavigationTelemetryQuality


def _metrics(*, feedback_samples: int = 3, distance_to_goal_m: float = 0.25) -> NavigationMetrics:
    return NavigationMetrics(
        path_length_m=1.0,
        distance_to_goal_m=distance_to_goal_m,
        stuck_events=0,
        feedback_samples=feedback_samples,
        recoveries=0,
    )


def _quality(
    *,
    received: int = 3,
    valid: int = 3,
    invalid: int = 0,
    final_pose_valid: bool = True,
) -> NavigationTelemetryQuality:
    return NavigationTelemetryQuality(
        received_feedback_samples=received,
        valid_pose_samples=valid,
        invalid_pose_samples=invalid,
        final_pose_valid=final_pose_valid,
    )


def test_evidence_passes_at_goal_tolerance_boundary() -> None:
    decision = evaluate_navigation_success(
        metrics=_metrics(distance_to_goal_m=0.25),
        telemetry_quality=_quality(),
        policy=NavigationEvidencePolicy(goal_tolerance_m=0.25),
    )

    assert decision.status == "PASS"
    assert decision.reason_code is None


def test_goal_tolerance_violation_is_robot_failure() -> None:
    decision = evaluate_navigation_success(
        metrics=_metrics(distance_to_goal_m=0.2504),
        telemetry_quality=_quality(),
        policy=NavigationEvidencePolicy(goal_tolerance_m=0.25),
    )

    assert decision.status == "FAIL"
    assert decision.reason_code == "goal_tolerance_exceeded"


@pytest.mark.parametrize(
    ("metrics", "quality", "reason_code"),
    [
        (
            _metrics(feedback_samples=0),
            _quality(received=0, valid=0, final_pose_valid=False),
            "insufficient_feedback",
        ),
        (_metrics(), _quality(received=2), "telemetry_sample_count_mismatch"),
        (_metrics(), _quality(valid=2), "telemetry_pose_count_mismatch"),
        (_metrics(), _quality(valid=2, invalid=1), "invalid_pose_feedback"),
        (_metrics(), _quality(final_pose_valid=False), "invalid_final_pose"),
    ],
)
def test_invalid_or_insufficient_evidence_is_infrastructure_error(
    metrics: NavigationMetrics,
    quality: NavigationTelemetryQuality,
    reason_code: str,
) -> None:
    decision = evaluate_navigation_success(
        metrics=metrics,
        telemetry_quality=quality,
        policy=NavigationEvidencePolicy(),
    )

    assert decision.status == "INFRA_ERROR"
    assert decision.reason_code == reason_code


@pytest.mark.parametrize(
    "kwargs",
    [
        {"goal_tolerance_m": 0.0},
        {"goal_tolerance_m": float("nan")},
        {"min_feedback_samples": 0},
        {"min_feedback_samples": True},
    ],
)
def test_evidence_policy_rejects_invalid_thresholds(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        NavigationEvidencePolicy(**kwargs)
