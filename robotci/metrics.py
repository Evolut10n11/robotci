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

        self._last_x = start_x
        self._last_y = start_y
        self._last_motion_at = started_at
        self._movement_epsilon_m = movement_epsilon_m
        self._stuck_after_sec = stuck_after_sec
        self._path_length_m = 0.0
        self._distance_remaining_m: float | None = None
        self._stuck_active = False
        self._stuck_events = 0
        self._feedback_samples = 0
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
        distance_remaining_m: float | None = None,
        recoveries: int | None = None,
    ) -> None:
        step_m = math.hypot(x - self._last_x, y - self._last_y)

        if step_m >= self._movement_epsilon_m:
            self._path_length_m += step_m
            self._last_motion_at = now
            self._stuck_active = False
        else:
            self.tick(now)

        self._last_x = x
        self._last_y = y
        self._feedback_samples += 1

        if (
            distance_remaining_m is not None
            and math.isfinite(distance_remaining_m)
            and distance_remaining_m >= 0
        ):
            self._distance_remaining_m = distance_remaining_m

        if recoveries is not None and recoveries >= 0:
            self._recoveries = max(self._recoveries, recoveries)

    def snapshot(self, *, goal_x: float, goal_y: float) -> NavigationMetrics:
        if self._distance_remaining_m is None:
            distance_to_goal_m = math.hypot(goal_x - self._last_x, goal_y - self._last_y)
        else:
            distance_to_goal_m = self._distance_remaining_m

        return NavigationMetrics(
            path_length_m=round(self._path_length_m, 3),
            distance_to_goal_m=round(distance_to_goal_m, 3),
            stuck_events=self._stuck_events,
            feedback_samples=self._feedback_samples,
            recoveries=self._recoveries,
        )
