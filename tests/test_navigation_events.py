"""Exercise the Nav2 adapter boundary without installing ROS in the core suite."""

from __future__ import annotations

import importlib.util
import json
import math
import sys
from enum import Enum
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from robotci.metrics import NavigationMetricsTracker
from robotci.replay import ReplayRecorder
from robotci.results import Pose2D
from robotci.viewer import load_replay


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
    spec = importlib.util.spec_from_file_location("navigation_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def feedback(stamp: int, x: float = 0, recoveries: int = 0):
    return NS(
        current_pose=NS(
            header=NS(stamp=NS(sec=stamp, nanosec=0)),
            pose=NS(position=NS(x=x, y=0), orientation=NS(x=0, y=0, z=0, w=1)),
        ),
        navigation_time=NS(sec=stamp, nanosec=0),
        number_of_recoveries=recoveries,
    )


def test_missing_and_cached_feedback_tick_once_and_invalid_pose_keeps_recovery(navigation):
    tracker = NavigationMetricsTracker(start_x=0, start_y=0, started_at=100)
    recorder = ReplayRecorder(
        scenario="route", start=Pose2D(0, 0), goal=Pose2D(1, 0), started_at=100,
    )
    navigator = NS(getFeedback=lambda: None)
    key = navigation._record_feedback(navigator, tracker, recorder, 105, None)
    navigator.getFeedback = lambda: feedback(1, x=math.nan, recoveries=3)
    key = navigation._record_feedback(navigator, tracker, recorder, 106, key)
    key = navigation._record_feedback(navigator, tracker, recorder, 107, key)
    assert [(e.type, e.observed_at, e.count) for e in tracker.events] == [
        ("STUCK", 105, 1), ("RECOVERY", 106, 3),
    ]
    assert tracker.telemetry_quality().received_feedback_samples == 1
    assert tracker.telemetry_quality().invalid_pose_samples == 1
    navigator.getFeedback = lambda: feedback(2, x=0.5, recoveries=3)
    key = navigation._record_feedback(navigator, tracker, recorder, 108, key)
    # A cached valid feedback sample must not add poses or new recoveries.
    navigation._record_feedback(navigator, tracker, recorder, 113, key)
    payload = recorder.build(
        status="TIMEOUT", duration_sec=14,
        metrics=tracker.snapshot(goal_x=1, goal_y=0),
        navigation_result="CANCELED_BY_TIMEOUT", events=tracker.events,
    )
    assert len(payload["samples"]) == 1
    assert payload["samples"][0]["t"] == 8
    assert [(e["type"], e["t"]) for e in payload["events"]] == [
        ("START", 0), ("STUCK", 5), ("RECOVERY", 6), ("STUCK", 13), ("FAIL", 14),
    ]
    assert payload["metrics"]["stuck_events"] == 2
    assert payload["metrics"]["recoveries"] == 3


def test_navigation_boundary_writes_observations_with_matching_result(navigation, tmp_path):
    class Navigator:
        def __init__(self, **kwargs):
            self.index = -1

        def get_clock(self):
            return NS(now=lambda: NS(to_msg=lambda: NS()))

        def goToPose(self, pose):
            return True

        def isTaskComplete(self):
            self.index += 1
            return self.index == 3

        def getFeedback(self):
            return [feedback(1), feedback(2), feedback(3, x=1, recoveries=2)][self.index]

        def getResult(self):
            return navigation.TaskResult.SUCCEEDED

        def destroy_node(self):
            pass

    times = iter([90, 100, 100.1, 105.2, 106.3, 107])
    navigation.time = NS(monotonic=lambda: next(times), sleep=lambda _: None)
    navigation.BasicNavigator = Navigator
    target = tmp_path / "result.json"
    assert navigation.run_navigation_scenario(
        "route", Pose2D(0, 0), Pose2D(1, 0), target, timeout_sec=30,
    ) == 0
    result = json.loads(target.read_text())
    replay = load_replay(tmp_path / "result.replay.json")
    assert [(e["type"], e["t"], e.get("count")) for e in replay["events"]] == [
        ("START", 0, None), ("STUCK", 5.2, 1), ("RECOVERY", 6.3, 2), ("GOAL", 7, None),
    ]
    assert result["metrics"]["stuck_events"] == replay["metrics"]["stuck_events"] == 1
    assert result["metrics"]["recoveries"] == replay["metrics"]["recoveries"] == 2
    assert [sample["t"] for sample in replay["samples"]] == [0.1, 5.2, 6.3]
    assert replay["samples"][1]["position"]["x"] == 0
    assert replay["samples"][2]["position"]["x"] == 1
