from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class NavigationMetrics:
    path_length_m: float
    distance_to_goal_m: float
    stuck_events: int
    feedback_samples: int
    recoveries: int


@dataclass(frozen=True)
class NavigationTelemetryQuality:
    received_feedback_samples: int
    valid_pose_samples: int
    invalid_pose_samples: int
    final_pose_valid: bool


def planar_yaw_from_quaternion(*, x: float, y: float, z: float, w: float) -> float:
    values = (x, y, z, w)
    if any(not math.isfinite(value) for value in values):
        return math.nan

    norm = math.hypot(*values)
    if not math.isfinite(norm) or norm <= 1e-12:
        return math.nan

    normalized_x, normalized_y, normalized_z, normalized_w = (
        value / norm for value in values
    )
    siny_cosp = 2.0 * (
        normalized_w * normalized_z + normalized_x * normalized_y
    )
    cosy_cosp = 1.0 - 2.0 * (
        normalized_y * normalized_y + normalized_z * normalized_z
    )
    return math.atan2(siny_cosp, cosy_cosp)


class NavigationMetricsTracker:
    """Accumulate navigation telemetry without importing ROS dependencies."""

    def __init__(
        self,
        *,
        start_x: float,
        start_y: float,
        started_at: float,
        movement_epsilon_m: float = 0.02,
        stuck_after_sec: float = 5.0,
    ) -> None:
        if movement_epsilon_m <= 0:
            raise ValueError("movement_epsilon_m must be greater than zero")
        if stuck_after_sec <= 0:
            raise ValueError("stuck_after_sec must be greater than zero")

        self._path_anchor_x = start_x
        self._path_anchor_y = start_y
        self._current_x = start_x
        self._current_y = start_y
        self._last_motion_at = started_at
        self._movement_epsilon_m = movement_epsilon_m
        self._stuck_after_sec = stuck_after_sec
        self._path_length_m = 0.0
        self._stuck_active = False
        self._stuck_events = 0
        self._feedback_samples = 0
        self._valid_pose_samples = 0
        self._invalid_pose_samples = 0
        self._final_pose_valid = False
        self._recoveries = 0

    def tick(self, now: float) -> None:
        """Advance stuck detection even when no new feedback sample arrives."""
        if self._stuck_active:
            return
        if now - self._last_motion_at < self._stuck_after_sec:
            return

        self._stuck_active = True
        self._stuck_events += 1

    def update(
        self,
        *,
        x: float,
        y: float,
        now: float,
        yaw: float | None = None,
        recoveries: int | None = None,
    ) -> bool:
        self._feedback_samples += 1
        if recoveries is not None and recoveries >= 0:
            # Nav2 reports a cumulative counter. Keep its high-water mark even
            # when the pose in the same feedback sample is malformed.
            self._recoveries = max(self._recoveries, recoveries)

        pose_values = (x, y) if yaw is None else (x, y, yaw)
        if any(not math.isfinite(value) for value in pose_values):
            self._invalid_pose_samples += 1
            self._final_pose_valid = False
            self.tick(now)
            return False

        self._valid_pose_samples += 1
        self._final_pose_valid = True
        self._current_x = x
        self._current_y = y

        # Compare against the last position that counted as real motion, not the
        # immediately previous feedback sample. Slow robots can legitimately move
        # less than the jitter threshold per sample; keeping the anchor in place
        # lets those small increments accumulate until they represent real motion.
        step_m = math.hypot(
            x - self._path_anchor_x,
            y - self._path_anchor_y,
        )

        if step_m >= self._movement_epsilon_m:
            self._path_length_m += step_m
            self._path_anchor_x = x
            self._path_anchor_y = y
            self._last_motion_at = now
            self._stuck_active = False
        else:
            self.tick(now)

        return True

    def snapshot(self, *, goal_x: float, goal_y: float) -> NavigationMetrics:
        # Nav2's distance_remaining follows its planned route and may be stale
        # when the task completes. Goal evidence instead uses the straight-line
        # distance from the latest valid feedback pose to the configured goal.
        distance_to_goal_m = math.hypot(
            goal_x - self._current_x,
            goal_y - self._current_y,
        )

        return NavigationMetrics(
            path_length_m=self._path_length_m,
            distance_to_goal_m=distance_to_goal_m,
            stuck_events=self._stuck_events,
            feedback_samples=self._feedback_samples,
            recoveries=self._recoveries,
        )

    def telemetry_quality(self) -> NavigationTelemetryQuality:
        return NavigationTelemetryQuality(
            received_feedback_samples=self._feedback_samples,
            valid_pose_samples=self._valid_pose_samples,
            invalid_pose_samples=self._invalid_pose_samples,
            final_pose_valid=self._final_pose_valid,
        )
