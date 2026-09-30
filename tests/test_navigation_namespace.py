"""Exercise namespaced action selection and missing-server evidence without ROS."""

from __future__ import annotations

import importlib.util
import itertools
import json
import sys
from enum import Enum
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from robotci.results import Pose2D
from robotci.ros_namespace import normalize_ros_namespace


@pytest.fixture
def navigation(monkeypatch):
    monkeypatch.delenv("ROBOTCI_ROS_NAMESPACE", raising=False)
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
    source = Path(__file__).parents[1] / "robotci/ros/navigation_scenario.py"
    spec = importlib.util.spec_from_file_location("navigation_namespace_under_test", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("supplied, expected", [
    ("", ""), ("/", ""), ("robot1", "/robot1"), ("/robot1", "/robot1"),
    ("fleet/robot_1", "/fleet/robot_1"), ("_robot", "/_robot"),
])
def test_namespace_has_one_canonical_graph_identity(supplied, expected):
    assert normalize_ros_namespace(supplied) == expected


@pytest.mark.parametrize("supplied", [
    "//robot", "/robot/", "robot//nav", "1robot", "robot/2nav", "robot-1",
    "robot name", " /robot", "~/robot", "{robot}", "robot:=value", "/机器人", None,
])
def test_invalid_namespace_is_rejected(supplied):
    with pytest.raises(ValueError, match="ROS namespace must"):
        normalize_ros_namespace(supplied)


def _run(navigation, tmp_path, *, namespace=None, available_namespace=""):
    calls = {"wait": [], "goals": [], "destroyed": False}

    class Navigator:
        def __init__(self, **kwargs):
            calls["constructor"] = kwargs
            self.namespace = kwargs["namespace"]
            self.nav_to_pose_client = NS(wait_for_server=self.wait_for_server)

        def wait_for_server(self, **kwargs):
            calls["wait"].append(kwargs)
            return self.namespace == available_namespace

        def get_clock(self):
            return NS(now=lambda: NS(to_msg=lambda: NS()))

        def goToPose(self, pose):
            calls["goals"].append(pose)
            return True

        def isTaskComplete(self):
            return True

        def getFeedback(self):
            return NS(
                current_pose=NS(
                    header=NS(stamp=NS(sec=1, nanosec=0)),
                    pose=NS(position=NS(x=1, y=0), orientation=NS(x=0, y=0, z=0, w=1)),
                ),
                navigation_time=NS(sec=1, nanosec=0),
                number_of_recoveries=0,
            )

        def getResult(self):
            return navigation.TaskResult.SUCCEEDED

        def destroy_node(self):
            calls["destroyed"] = True

    clock = itertools.count(100, 0.1)
    navigation.time = NS(monotonic=lambda: next(clock), sleep=lambda _: None)
    navigation.BasicNavigator = Navigator
    target = tmp_path / "result.json"
    exit_code = navigation.run_navigation_scenario(
        "route", Pose2D(0, 0), Pose2D(1, 0), target,
        timeout_sec=30, namespace=namespace,
    )
    result = json.loads(target.read_text())
    replay = json.loads(target.with_name("result.replay.json").read_text())
    return exit_code, result, replay, calls


@pytest.mark.parametrize("namespace", [None, "", "/"])
def test_default_graph_keeps_root_action_and_map_frame(navigation, tmp_path, namespace):
    exit_code, result, _, calls = _run(navigation, tmp_path, namespace=namespace)
    assert exit_code == navigation.EXIT_PASS
    assert result["status"] == "PASS"
    assert calls["constructor"]["namespace"] == ""
    assert calls["wait"] == [{"timeout_sec": 30.0}]
    assert calls["goals"][0].header.frame_id == "map"
    assert calls["destroyed"]


def test_environment_namespace_selects_action_and_preserves_final_evidence(
    navigation, tmp_path, monkeypatch,
):
    monkeypatch.setenv("ROBOTCI_ROS_NAMESPACE", "fleet/robot1")
    exit_code, result, replay, calls = _run(
        navigation, tmp_path, available_namespace="/fleet/robot1",
    )
    assert exit_code == navigation.EXIT_PASS
    assert calls["constructor"]["namespace"] == "/fleet/robot1"
    assert result["metrics"]["distance_to_goal_m"] == 0
    assert result["telemetry_quality"]["valid_pose_samples"] == 1
    assert replay["samples"][0]["position"]["x"] == 1


def test_explicit_namespace_overrides_inherited_setting(navigation, tmp_path, monkeypatch):
    monkeypatch.setenv("ROBOTCI_ROS_NAMESPACE", "/wrong")
    exit_code, _, _, calls = _run(
        navigation, tmp_path, namespace="robot1", available_namespace="/robot1",
    )
    assert exit_code == navigation.EXIT_PASS
    assert calls["constructor"]["namespace"] == "/robot1"


def test_wrong_namespace_is_bounded_infrastructure_error_before_goal_dispatch(
    navigation, tmp_path,
):
    exit_code, result, replay, calls = _run(
        navigation, tmp_path, namespace="/wrong", available_namespace="/robot1",
    )
    assert exit_code == navigation.EXIT_INFRA_ERROR
    assert result["status"] == "INFRA_ERROR"
    assert replay["status"] == "FAIL"  # Replay v1 folds infrastructure into its failure state.
    assert result["reason_code"] == "navigation_server_unavailable"
    assert result["navigation_result"] == "NAVIGATION_SERVER_UNAVAILABLE: /wrong/navigate_to_pose"
    assert calls["wait"] == [{"timeout_sec": 30.0}]
    assert calls["goals"] == []
    assert calls["destroyed"]
    assert replay["samples"] == []


def test_invalid_environment_namespace_fails_before_ros_initialization(
    navigation, tmp_path, monkeypatch,
):
    monkeypatch.setenv("ROBOTCI_ROS_NAMESPACE", "/bad//name")
    initialized = []
    navigation.rclpy.init = lambda **kwargs: initialized.append(kwargs)
    with pytest.raises(ValueError, match="ROS namespace must"):
        navigation.run_navigation_scenario(
            "route", Pose2D(0, 0), Pose2D(1, 0), tmp_path / "result.json", timeout_sec=30,
        )
    assert initialized == []
    assert not (tmp_path / "result.json").exists()


def test_probe_cli_passes_explicit_namespace(navigation, tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "argv", [
        "navigation_scenario", "--scenario", "route", "--start-x", "0", "--start-y", "0",
        "--goal-x", "1", "--goal-y", "0", "--output", str(tmp_path / "result.json"),
        "--timeout-sec", "30", "--namespace", "/robot1",
    ])
    called = []
    navigation.run_navigation_scenario = lambda **kwargs: called.append(kwargs) or 0
    assert navigation.main() == 0
    assert called[0]["namespace"] == "/robot1"


def test_invalid_namespace_run_api_and_cli_fail_before_process_creation(tmp_path, monkeypatch):
    from typer.testing import CliRunner

    from robotci import runner
    from robotci.cli import app

    configuration = tmp_path / "robotci.yaml"
    configuration.write_text(
        "version: 1\nruntime: native\nscenarios:\n"
        "  - name: route\n    start: {x: 0, y: 0}\n    goal: {x: 1, y: 0}\n"
        "    map_id: warehouse\n    timeout_sec: 30\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("ROBOTCI_ROS_NAMESPACE", "/invalid//namespace")
    monkeypatch.setattr(runner, "select_runtime", lambda requested: "native")

    def unexpected_runtime(*args, **kwargs):
        raise AssertionError("Invalid namespace must be rejected before starting native runtime")

    monkeypatch.setattr(runner, "run_runtime_process", unexpected_runtime)
    with pytest.raises(runner.RuntimeUnavailableError, match="invalid ROBOTCI_ROS_NAMESPACE"):
        runner.run_scenario(
            scenario="route", runtime="native", config_path=configuration,
            output=tmp_path / "result.json",
        )
    result = CliRunner().invoke(app, [
        "run", "--runtime", "native", "--scenario", "route", "--config", str(configuration),
        "--output", str(tmp_path / "result.json"),
    ])
    assert result.exit_code == 3
    assert "invalid ROBOTCI_ROS_NAMESPACE" in result.output
    assert not (tmp_path / "result.json").exists()
