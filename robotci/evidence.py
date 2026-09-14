from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

from robotci.metrics import NavigationMetrics, NavigationTelemetryQuality

EvidenceStatus = Literal["PASS", "FAIL", "INFRA_ERROR"]


@dataclass(frozen=True)
class NavigationEvidencePolicy:
    goal_tolerance_m: float = 0.25
    min_feedback_samples: int = 1

    def __post_init__(self) -> None:
        try:
            tolerance_is_valid = (
                not isinstance(self.goal_tolerance_m, bool)
                and isinstance(self.goal_tolerance_m, int | float)
                and math.isfinite(float(self.goal_tolerance_m))
                and self.goal_tolerance_m > 0
            )
        except OverflowError:
            tolerance_is_valid = False
        if not tolerance_is_valid:
            raise ValueError("goal_tolerance_m must be a finite number greater than zero")
        if (
            isinstance(self.min_feedback_samples, bool)
            or not isinstance(self.min_feedback_samples, int)
            or self.min_feedback_samples <= 0
        ):
            raise ValueError("min_feedback_samples must be a positive integer")


@dataclass(frozen=True)
class EvidenceDecision:
    status: EvidenceStatus
    reason_code: str | None = None


def evaluate_navigation_success(
    *,
    metrics: NavigationMetrics,
    telemetry_quality: NavigationTelemetryQuality,
    policy: NavigationEvidencePolicy,
) -> EvidenceDecision:
    """Turn Nav2 success plus measured evidence into a deterministic verdict."""

    if telemetry_quality.received_feedback_samples != metrics.feedback_samples:
        return EvidenceDecision("INFRA_ERROR", "telemetry_sample_count_mismatch")
    if (
        telemetry_quality.valid_pose_samples
        + telemetry_quality.invalid_pose_samples
        != telemetry_quality.received_feedback_samples
    ):
        return EvidenceDecision("INFRA_ERROR", "telemetry_pose_count_mismatch")
    if metrics.feedback_samples < policy.min_feedback_samples:
        return EvidenceDecision("INFRA_ERROR", "insufficient_feedback")
    if telemetry_quality.invalid_pose_samples > 0:
        return EvidenceDecision("INFRA_ERROR", "invalid_pose_feedback")
    if telemetry_quality.valid_pose_samples < policy.min_feedback_samples:
        return EvidenceDecision("INFRA_ERROR", "insufficient_valid_pose_feedback")
    if not telemetry_quality.final_pose_valid:
        return EvidenceDecision("INFRA_ERROR", "invalid_final_pose")
    if metrics.distance_to_goal_m > policy.goal_tolerance_m:
        return EvidenceDecision("FAIL", "goal_tolerance_exceeded")
    return EvidenceDecision("PASS")
