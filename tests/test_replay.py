from __future__ import annotations

from robotci.metrics import NavigationMetrics
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
