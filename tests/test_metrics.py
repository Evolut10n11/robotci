from __future__ import annotations

from robotci.metrics import NavigationMetricsTracker


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
        distance_remaining_m=2.0,
        recoveries=0,
    )
    tracker.update(
        x=3.0,
        y=4.0,
        now=2.0,
        distance_remaining_m=1.25,
        recoveries=1,
    )

    metrics = tracker.snapshot(goal_x=4.0, goal_y=4.0)

    assert metrics.path_length_m == 7.0
    assert metrics.distance_to_goal_m == 1.25
    assert metrics.feedback_samples == 2
    assert metrics.recoveries == 1
    assert metrics.stuck_events == 0


def test_metrics_tracker_falls_back_to_euclidean_goal_distance() -> None:
    tracker = NavigationMetricsTracker(
        start_x=0.0,
        start_y=0.0,
        started_at=0.0,
    )
    tracker.update(x=3.0, y=4.0, now=1.0)

    metrics = tracker.snapshot(goal_x=6.0, goal_y=8.0)

    assert metrics.distance_to_goal_m == 5.0


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
    assert metrics.feedback_samples == 5
    assert metrics.stuck_events == 0
