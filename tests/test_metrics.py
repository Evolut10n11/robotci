from __future__ import annotations

import math

import pytest

from robotci.metrics import NavigationEvent, NavigationMetricsTracker, planar_yaw_from_quaternion


def test_metrics_tracker_accumulates_path_and_goal_distance() -> None:
    tracker = NavigationMetricsTracker(
        start_x=0.0,
        start_y=0.0,
        started_at=0.0,
    )

    tracker.update(
        x=3.0,
        y=0.0,
        now=1.0,
        recoveries=0,
    )
    tracker.update(
        x=3.0,
        y=4.0,
        now=2.0,
        recoveries=1,
    )

    metrics = tracker.snapshot(goal_x=4.0, goal_y=4.0)

    assert metrics.path_length_m == 7.0
    assert metrics.distance_to_goal_m == 1.0
    assert metrics.feedback_samples == 2
    assert metrics.recoveries == 1
    assert metrics.stuck_events == 0


def test_metrics_tracker_uses_latest_pose_for_euclidean_goal_distance() -> None:
    tracker = NavigationMetricsTracker(
        start_x=0.0,
        start_y=0.0,
        started_at=0.0,
    )
    tracker.update(x=3.0, y=4.0, now=1.0)

    metrics = tracker.snapshot(goal_x=6.0, goal_y=8.0)

    assert metrics.distance_to_goal_m == 5.0


def test_metrics_tracker_preserves_distance_precision_for_verdicts() -> None:
    tracker = NavigationMetricsTracker(
        start_x=0.0,
        start_y=0.0,
        started_at=0.0,
    )
    tracker.update(x=0.7496, y=0.0, now=1.0)

    metrics = tracker.snapshot(goal_x=1.0, goal_y=0.0)

    assert metrics.distance_to_goal_m == pytest.approx(0.2504)


def test_metrics_tracker_records_one_stuck_event_until_motion_resumes() -> None:
    tracker = NavigationMetricsTracker(
        start_x=0.0,
        start_y=0.0,
        started_at=0.0,
        stuck_after_sec=5.0,
    )

    tracker.tick(5.1)
    tracker.tick(8.0)

    first = tracker.snapshot(goal_x=1.0, goal_y=0.0)
    assert first.stuck_events == 1

    tracker.update(x=0.5, y=0.0, now=9.0)
    tracker.tick(14.1)

    second = tracker.snapshot(goal_x=1.0, goal_y=0.0)
    assert second.stuck_events == 2
    assert tracker.events == (
        NavigationEvent(5.1, "STUCK"),
        NavigationEvent(14.1, "STUCK"),
    )


def test_metrics_tracker_ignores_tiny_pose_jitter_for_path_length() -> None:
    tracker = NavigationMetricsTracker(
        start_x=0.0,
        start_y=0.0,
        started_at=0.0,
        movement_epsilon_m=0.02,
    )

    tracker.update(x=0.005, y=0.0, now=1.0)
    tracker.update(x=-0.005, y=0.0, now=2.0)
    tracker.update(x=0.004, y=0.0, now=3.0)

    metrics = tracker.snapshot(goal_x=1.0, goal_y=0.0)

    assert metrics.path_length_m == 0.0
    assert metrics.distance_to_goal_m == pytest.approx(0.996)
    assert metrics.feedback_samples == 3


def test_metrics_tracker_accumulates_slow_motion_below_per_sample_epsilon() -> None:
    tracker = NavigationMetricsTracker(
        start_x=0.0,
        start_y=0.0,
        started_at=0.0,
        movement_epsilon_m=0.02,
    )

    tracker.update(x=0.009, y=0.0, now=0.1)
    tracker.update(x=0.018, y=0.0, now=0.2)
    tracker.update(x=0.027, y=0.0, now=0.3)
    tracker.update(x=0.036, y=0.0, now=0.4)
    tracker.update(x=0.045, y=0.0, now=0.5)

    metrics = tracker.snapshot(goal_x=1.0, goal_y=0.0)

    # Motion is accumulated once net displacement crosses the 2 cm deadband.
    # The remaining 1.8 cm stays below the jitter threshold and is intentionally
    # not added until a later sample moves far enough from the last accepted pose.
    assert metrics.path_length_m == 0.027
    assert metrics.distance_to_goal_m == pytest.approx(0.955)
    assert metrics.feedback_samples == 5
    assert metrics.stuck_events == 0


def test_metrics_tracker_rejects_non_finite_pose_without_poisoning_metrics() -> None:
    tracker = NavigationMetricsTracker(
        start_x=0.0,
        start_y=0.0,
        started_at=0.0,
    )

    accepted = tracker.update(x=math.nan, y=1.0, yaw=0.0, now=1.0)
    metrics = tracker.snapshot(goal_x=1.0, goal_y=0.0)
    quality = tracker.telemetry_quality()

    assert accepted is False
    assert metrics.path_length_m == 0.0
    assert metrics.distance_to_goal_m == 1.0
    assert metrics.feedback_samples == 1
    assert quality.received_feedback_samples == 1
    assert quality.valid_pose_samples == 0
    assert quality.invalid_pose_samples == 1
    assert quality.final_pose_valid is False


def test_metrics_tracker_marks_latest_valid_pose() -> None:
    tracker = NavigationMetricsTracker(
        start_x=0.0,
        start_y=0.0,
        started_at=0.0,
    )

    tracker.update(x=math.inf, y=0.0, yaw=0.0, now=1.0)
    tracker.update(x=0.5, y=0.0, yaw=0.0, now=2.0)

    quality = tracker.telemetry_quality()
    assert quality.received_feedback_samples == 2
    assert quality.valid_pose_samples == 1
    assert quality.invalid_pose_samples == 1
    assert quality.final_pose_valid is True


def test_metrics_tracker_keeps_recovery_high_water_mark_with_invalid_pose() -> None:
    tracker = NavigationMetricsTracker(
        start_x=0.0,
        start_y=0.0,
        started_at=0.0,
    )

    tracker.update(x=0.5, y=0.0, now=1.0, recoveries=3)
    tracker.update(x=math.nan, y=0.0, now=2.0, recoveries=4)
    tracker.update(x=0.75, y=0.0, now=3.0, recoveries=2)

    metrics = tracker.snapshot(goal_x=1.0, goal_y=0.0)

    assert metrics.recoveries == 4
    assert metrics.distance_to_goal_m == 0.25
    assert tracker.events == (
        NavigationEvent(1.0, "RECOVERY", 3),
        NavigationEvent(2.0, "RECOVERY", 1),
    )


def test_repeated_feedback_does_not_duplicate_counter_observations() -> None:
    tracker = NavigationMetricsTracker(start_x=0, start_y=0, started_at=100)
    tracker.update(x=0, y=0, now=105, recoveries=2)
    snapshot = tracker.events
    tracker.update(x=0, y=0, now=106, recoveries=2)
    tracker.tick(107)
    tracker.update(x=1, y=0, now=108, recoveries=1)
    tracker.update(x=1, y=0, now=109, recoveries=3)
    assert snapshot == (NavigationEvent(105, "RECOVERY", 2), NavigationEvent(105, "STUCK"))
    assert tracker.events == (*snapshot, NavigationEvent(109, "RECOVERY"))
    metrics = tracker.snapshot(goal_x=1, goal_y=0)
    assert sum(e.count for e in tracker.events if e.type == "STUCK") == metrics.stuck_events
    assert sum(e.count for e in tracker.events if e.type == "RECOVERY") == metrics.recoveries


def test_planar_yaw_normalizes_a_finite_quaternion() -> None:
    yaw = planar_yaw_from_quaternion(x=0.0, y=0.0, z=math.sqrt(2), w=math.sqrt(2))

    assert yaw == pytest.approx(math.pi / 2)


@pytest.mark.parametrize(
    "values",
    [
        {"x": 0.0, "y": 0.0, "z": 0.0, "w": 0.0},
        {"x": math.nan, "y": 0.0, "z": 0.0, "w": 1.0},
    ],
)
def test_planar_yaw_marks_invalid_quaternion(values: dict[str, float]) -> None:
    assert math.isnan(planar_yaw_from_quaternion(**values))
