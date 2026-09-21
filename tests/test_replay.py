from __future__ import annotations

import pytest

from robotci.metrics import NavigationMetrics, NavigationMetricsTracker
from robotci.replay import ReplayRecorder, default_replay_path, write_replay
from robotci.results import Pose2D
from robotci.viewer import load_replay, validate_replay


def _metrics() -> NavigationMetrics:
    return NavigationMetrics(
        path_length_m=1.25,
        distance_to_goal_m=0.4,
        stuck_events=1,
        feedback_samples=2,
        recoveries=1,
    )


def test_replay_recorder_builds_viewer_payload() -> None:
    recorder = ReplayRecorder(
        scenario="simple_route",
        start=Pose2D(0.0, 0.0, 0.0),
        goal=Pose2D(2.0, 1.0, 0.2),
        started_at=100.0,
    )
    recorder.record(x=0.5, y=0.2, yaw=0.1, now=101.25)
    recorder.record(x=1.5, y=0.8, yaw=0.15, now=102.5)

    payload = recorder.build(
        status="PASS",
        duration_sec=3.0,
        metrics=_metrics(),
        navigation_result="SUCCEEDED",
    )

    assert validate_replay(payload) == payload
    assert payload["status"] == "PASS"
    assert payload["result_status"] == "PASS"
    assert payload["samples"][0]["t"] == 0.0
    assert payload["samples"][-1]["position"]["x"] == 1.5
    assert payload["events"][-1]["type"] == "GOAL"


def test_replay_normalizes_timeout_for_viewer() -> None:
    recorder = ReplayRecorder(
        scenario="blocked_route",
        start=Pose2D(1.0, 2.0, 0.4),
        goal=Pose2D(5.0, 6.0, 0.0),
        started_at=10.0,
    )

    payload = recorder.build(
        status="TIMEOUT",
        duration_sec=0.0,
        metrics=_metrics(),
        navigation_result="CANCELED_BY_TIMEOUT",
    )

    assert payload["status"] == "FAIL"
    assert payload["result_status"] == "TIMEOUT"
    assert len(payload["samples"]) == 2
    assert payload["duration_sec"] > 0
    assert validate_replay(payload) == payload


def test_replay_path_and_round_trip(tmp_path) -> None:
    result_path = tmp_path / "result.json"
    replay_path = default_replay_path(result_path)
    assert replay_path.name == "result.replay.json"

    recorder = ReplayRecorder(
        scenario="simple_route",
        start=Pose2D(0.0, 0.0),
        goal=Pose2D(1.0, 0.0),
        started_at=1.0,
    )
    payload = recorder.build(
        status="FAIL",
        duration_sec=1.0,
        metrics=_metrics(),
        navigation_result="FAILED",
    )

    written = write_replay(payload, replay_path)
    assert written == replay_path
    assert load_replay(replay_path) == payload


@pytest.mark.parametrize("status", ["PASS", "FAIL", "TIMEOUT", "INFRA_ERROR"])
def test_observed_events_survive_finalization_and_round_trip(tmp_path, status) -> None:
    tracker = NavigationMetricsTracker(start_x=0, start_y=0, started_at=100)
    recorder = ReplayRecorder(
        scenario="route", start=Pose2D(0, 0), goal=Pose2D(1, 0), started_at=100,
    )
    tracker.update(x=0, y=0, now=101, recoveries=0)
    recorder.record(x=0, y=0, yaw=0, now=101)
    tracker.tick(105.125)
    tracker.tick(106)
    tracker.update(x=1, y=0, now=107.25, recoveries=3)
    recorder.record(x=1, y=0, yaw=0, now=107.25)
    metrics = tracker.snapshot(goal_x=1, goal_y=0)
    payload = recorder.build(
        status=status, duration_sec=8, metrics=metrics, navigation_result="test",
        events=tracker.events,
    )
    path = write_replay(payload, tmp_path / "route.replay.json")
    recorded = load_replay(path)
    assert [(e["type"], e["t"], e.get("count")) for e in recorded["events"]] == [
        ("START", 0, None), ("STUCK", 5.125, 1), ("RECOVERY", 7.25, 3),
        ("GOAL" if status == "PASS" else "FAIL", 8, None),
    ]
    assert recorded["result_status"] == status
    assert recorded["metrics"]["recoveries"] == 3
    assert recorded["metrics"]["stuck_events"] == 1
    # Finalization reads observations; it never consumes or duplicates them.
    assert recorder.build(
        status=status, duration_sec=8, metrics=metrics, navigation_result="test",
        events=tracker.events,
    ) == payload


@pytest.mark.parametrize("count", [0, -1, True, 1.5, "2", None, 2**53])
def test_replay_rejects_invalid_event_counter_delta(count) -> None:
    from robotci.viewer import ViewerError, demo_replay

    replay = demo_replay()
    replay["events"][1]["count"] = count
    with pytest.raises(ViewerError, match="count"):
        validate_replay(replay)


def test_legacy_replay_metrics_do_not_create_fabricated_events() -> None:
    recorder = ReplayRecorder(
        scenario="legacy", start=Pose2D(0, 0), goal=Pose2D(1, 0), started_at=0,
    )
    payload = recorder.build(
        status="PASS", duration_sec=10, metrics=_metrics(), navigation_result="SUCCEEDED",
    )
    assert [e["type"] for e in payload["events"]] == ["START", "GOAL"]
