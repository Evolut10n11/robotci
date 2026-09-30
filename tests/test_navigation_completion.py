"""Cover final Nav2 feedback delivered while the completion poll spins ROS."""

from __future__ import annotations

import importlib.util
import itertools
import json
import math
import sys
from enum import Enum
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from robotci.results import Pose2D


@pytest.fixture
def navigation(monkeypatch):
    result_type = Enum("TaskResult", "SUCCEEDED CANCELED FAILED UNKNOWN")
    monkeypatch.setitem(sys.modules, "rclpy", NS(init=lambda **kw: None, ok=lambda: False))
    monkeypatch.setitem(sys.modules, "geometry_msgs", NS())
    monkeypatch.setitem(sys.modules, "geometry_msgs.msg", NS(
        PoseStamped=lambda: NS(header=NS(), pose=NS(position=NS(), orientation=NS())),
    ))
    monkeypatch.setitem(sys.modules, "nav2_simple_commander", NS())
    monkeypatch.setitem(sys.modules, "nav2_simple_commander.robot_navigator", NS(
        BasicNavigator=object, TaskResult=result_type,
    ))
    path = Path(__file__).parents[1] / "robotci/ros/navigation_scenario.py"
    spec = importlib.util.spec_from_file_location("navigation_completion_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _feedback(stamp: int, *, x: float, recoveries: int = 0, valid_orientation: bool = True):
    return NS(
        current_pose=NS(
            header=NS(stamp=NS(sec=stamp, nanosec=0)),
            pose=NS(
                position=NS(x=x, y=0),
                orientation=NS(x=0, y=0, z=0, w=1 if valid_orientation else 0),
            ),
        ),
        navigation_time=NS(sec=stamp, nanosec=0),
        number_of_recoveries=recoveries,
    )


def _run(
    navigation, tmp_path, frames, *, min_feedback_samples: int = 1, clock=None,
    timeout_sec: float = 30,
):
    class Navigator:
        def __init__(self, **kwargs):
            self.frames = iter(frames)
            self.feedback = None
            self.nav_to_pose_client = NS(wait_for_server=lambda **kwargs: True)

        def get_clock(self):
            return NS(now=lambda: NS(to_msg=lambda: NS()))

        def goToPose(self, pose):
            return True

        def isTaskComplete(self):
            complete, self.feedback = next(self.frames)
            return complete

        def getFeedback(self):
            return self.feedback

        def getResult(self):
            return navigation.TaskResult.SUCCEEDED

        def cancelTask(self):
            raise AssertionError("Completed tasks should not be canceled")

        def destroy_node(self):
            pass

    clock = itertools.count(100, 0.1) if clock is None else iter(clock)
    navigation.time = NS(monotonic=lambda: next(clock), sleep=lambda _: None)
    navigation.BasicNavigator = Navigator
    target = tmp_path / "result.json"
    exit_code = navigation.run_navigation_scenario(
        "route", Pose2D(0, 0), Pose2D(1, 0), target, timeout_sec=timeout_sec,
        min_feedback_samples=min_feedback_samples,
    )
    result = json.loads(target.read_text())
    replay = json.loads(target.with_name("result.replay.json").read_text())
    return exit_code, result, replay


def test_completion_poll_captures_new_goal_pose_and_recoveries(navigation, tmp_path):
    exit_code, result, replay = _run(navigation, tmp_path, [
        (False, _feedback(1, x=0.35)),
        (True, _feedback(2, x=1, recoveries=2)),
    ])

    assert exit_code == navigation.EXIT_PASS
    assert result["status"] == "PASS"
    assert result["metrics"]["distance_to_goal_m"] == 0
    assert result["metrics"]["path_length_m"] == 1
    assert result["metrics"]["feedback_samples"] == 2
    assert result["metrics"]["recoveries"] == replay["metrics"]["recoveries"] == 2
    assert [sample["position"]["x"] for sample in replay["samples"]] == [0.35, 1]
    assert [sample["t"] for sample in replay["samples"]] == [0.1, 0.2]
    assert [(event["t"], event["count"]) for event in replay["events"]
            if event["type"] == "RECOVERY"] == [(0.2, 2)]


def test_immediately_completed_task_still_collects_observed_feedback(navigation, tmp_path):
    exit_code, result, replay = _run(navigation, tmp_path, [
        (True, _feedback(1, x=1)),
    ])

    assert exit_code == navigation.EXIT_PASS
    assert result["telemetry_quality"]["valid_pose_samples"] == 1
    assert replay["samples"][0]["position"]["x"] == 1


@pytest.mark.parametrize("completed_at, expected_status", [
    (109.9, "PASS"), (110, "TIMEOUT"), (110.1, "TIMEOUT"),
])
def test_completion_deadline_preserves_evidence_and_enforces_wall_clock_limit(
    navigation, tmp_path, completed_at, expected_status,
):
    exit_code, result, replay = _run(navigation, tmp_path, [
        (False, _feedback(1, x=0.35)),
        (True, _feedback(2, x=1, recoveries=2)),
    ], clock=[90, 100, 101, completed_at, completed_at + 0.1], timeout_sec=10)

    assert result["status"] == expected_status
    if expected_status == "TIMEOUT":
        assert exit_code == navigation.EXIT_TIMEOUT
        assert result["reason_code"] == "timeout"
        assert result["navigation_result"] == "COMPLETED_AFTER_TIMEOUT"
    else:
        assert exit_code == navigation.EXIT_PASS
        assert result.get("reason_code") is None
        assert result["navigation_result"] == "SUCCEEDED"
    assert result["metrics"]["distance_to_goal_m"] == 0
    assert result["metrics"]["path_length_m"] == replay["metrics"]["path_length_m"] == 1
    assert result["metrics"]["recoveries"] == replay["metrics"]["recoveries"] == 2
    assert [sample["position"]["x"] for sample in replay["samples"]] == [0.35, 1]


@pytest.mark.parametrize("minimum, expected_status", [(1, "PASS"), (2, "INFRA_ERROR")])
def test_cached_completion_feedback_does_not_inflate_evidence(
    navigation, tmp_path, minimum, expected_status,
):
    observed = _feedback(1, x=1, recoveries=3)
    _, result, replay = _run(navigation, tmp_path, [
        (False, observed), (True, observed),
    ], min_feedback_samples=minimum)

    assert result["status"] == expected_status
    assert result["metrics"]["feedback_samples"] == 1
    assert result["metrics"]["path_length_m"] == 1
    assert result["telemetry_quality"]["valid_pose_samples"] == 1
    assert len(replay["samples"]) == 1
    assert [event["count"] for event in replay["events"]
            if event["type"] == "RECOVERY"] == [3]
    if minimum == 2:
        assert result["reason_code"] == "insufficient_feedback"


def test_completion_feedback_retains_recovery_change_with_same_pose_timestamps(
    navigation, tmp_path,
):
    _, result, replay = _run(navigation, tmp_path, [
        (False, _feedback(1, x=1, recoveries=2)),
        (True, _feedback(1, x=1, recoveries=7)),
    ])

    assert result["status"] == "PASS"
    assert result["metrics"]["recoveries"] == 7
    assert result["metrics"]["path_length_m"] == 1
    assert result["metrics"]["feedback_samples"] == 2
    assert [event["count"] for event in replay["events"]
            if event["type"] == "RECOVERY"] == [2, 5]


@pytest.mark.parametrize("invalid_feedback", [
    _feedback(2, x=math.nan, recoveries=4),
    _feedback(2, x=1, recoveries=4, valid_orientation=False),
])
def test_invalid_final_pose_keeps_observed_path_and_recoveries(
    navigation, tmp_path, invalid_feedback,
):
    exit_code, result, replay = _run(navigation, tmp_path, [
        (False, _feedback(1, x=0.6)), (True, invalid_feedback),
    ])

    assert exit_code == navigation.EXIT_INFRA_ERROR
    assert result["reason_code"] == "invalid_pose_feedback"
    assert result["telemetry_quality"] == {
        "received_feedback_samples": 2,
        "valid_pose_samples": 1,
        "invalid_pose_samples": 1,
        "final_pose_valid": False,
    }
    assert result["metrics"]["path_length_m"] == 0.6
    assert result["metrics"]["distance_to_goal_m"] == 0.4
    assert result["metrics"]["recoveries"] == replay["metrics"]["recoveries"] == 4
    assert [sample["position"]["x"] for sample in replay["samples"]] == [0.6]


def test_missing_completion_feedback_never_substitutes_goal_pose(navigation, tmp_path):
    exit_code, result, replay = _run(navigation, tmp_path, [
        (False, _feedback(1, x=0.5)), (True, None),
    ])

    assert exit_code == navigation.EXIT_FAIL
    assert result["reason_code"] == "goal_tolerance_exceeded"
    assert result["metrics"]["distance_to_goal_m"] == 0.5
    assert result["metrics"]["feedback_samples"] == 1
    assert [sample["position"]["x"] for sample in replay["samples"]] == [0.5]


def test_success_without_any_pose_feedback_remains_infrastructure_error(navigation, tmp_path):
    exit_code, result, replay = _run(navigation, tmp_path, [(True, None)])

    assert exit_code == navigation.EXIT_INFRA_ERROR
    assert result["reason_code"] == "insufficient_feedback"
    assert result["metrics"]["feedback_samples"] == 0
    assert result["telemetry_quality"]["final_pose_valid"] is False
    assert replay["samples"] == []


@pytest.mark.parametrize("timeout", [
    0, -1, math.nan, math.inf, -math.inf, True, False, "30", None, 10**1000,
])
def test_direct_runtime_rejects_invalid_timeout_before_initializing_ros(
    navigation, tmp_path, timeout,
):
    initialized = []
    navigation.rclpy.init = lambda **kwargs: initialized.append(kwargs)

    with pytest.raises(ValueError, match="timeout_sec must be a finite number greater than zero"):
        navigation.run_navigation_scenario(
            "route", Pose2D(0, 0), Pose2D(1, 0), tmp_path / "result.json", timeout_sec=timeout,
        )

    assert initialized == []
    assert not (tmp_path / "result.json").exists()
