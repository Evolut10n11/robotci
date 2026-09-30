from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import signal
import subprocess
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from robotci.ros import gazebo_cleanup
from robotci.ros.gazebo_readiness import (
    asset_manifest,
    main,
    map_pose_is_free,
    parse_gazebo_pose,
    pose_matches,
    sha256_file,
    sha256_tree,
)


@pytest.mark.parametrize("separator", [" ", " | "])
def test_parse_actual_harmonic_model_pose(separator: str) -> None:
    # gz-sim8/src/cmd/ModelCommandAPI.cc poseInfo emits space-separated XYZ/RPY.
    output = (
        "Requesting state for world [depot]...\nModel: [8]\n"
        "  - Name: nav2_turtlebot4\n"
        "  - Pose [ XYZ (m) ] [ RPY (rad) ]:\n"
        f"    [{separator.join(['0.000001', '-0.002', '0.010000'])}]\n"
        f"    [{separator.join(['0.000000', '0.000000', '-3.14'])}]\n"
    )
    assert parse_gazebo_pose(output) == {"x": 0.000001, "y": -0.002, "yaw": -3.14}


@pytest.mark.parametrize("output", [
    "",
    "- Name: different_robot\n- Pose [ XYZ (m) ] [ RPY (rad) ]:\n[0 0 0]\n[0 0 0]",
    "- Name: nav2_turtlebot4\n- Pose [ XYZ (m) ] [ RPY (rad) ]:\n[nan 0 0]\n[0 0 0]",
    "- Name: nav2_turtlebot4\n- Pose [ XYZ (m) ] [ RPY (rad) ]:\n[0 0]\n[0 0 0]",
])
def test_physical_pose_requires_exact_model_and_valid_pose(output: str) -> None:
    with pytest.raises(ValueError):
        parse_gazebo_pose(output)


def test_start_verification_checks_position_and_wrapped_yaw() -> None:
    start = {"x": 0.0, "y": 0.0, "yaw": math.pi - 0.02}
    assert pose_matches(start, {"x": 0.04, "y": -0.05, "yaw": -math.pi + 0.02})
    assert not pose_matches(start, {"x": 0.2, "y": 0.0, "yaw": start["yaw"]})
    assert not pose_matches(start, {"x": 0.0, "y": 0.0, "yaw": start["yaw"] - 0.2})
    assert not pose_matches(start, {"x": float("nan"), "y": 0.0, "yaw": 0.0})


def _map() -> SimpleNamespace:
    return SimpleNamespace(
        info=SimpleNamespace(
            resolution=0.1, width=40, height=40,
            origin=SimpleNamespace(
                position=SimpleNamespace(x=-2.0, y=-2.0),
                orientation=SimpleNamespace(x=0.0, y=0.0, z=0.0, w=1.0),
            ),
        ),
        data=[0] * 1600,
    )


@pytest.mark.parametrize("blocked", [-1, 50, 100])
def test_map_checks_entire_footprint_not_only_center(blocked: int) -> None:
    grid = _map()
    assert map_pose_is_free(grid, 0.0, 0.0)
    grid.data[20 * 40 + 23] = blocked
    assert not map_pose_is_free(grid, 0.0, 0.0)


def test_map_rejects_outside_unknown_and_bad_resolution() -> None:
    grid = _map()
    assert not map_pose_is_free(grid, -1.8, 0.0)
    grid.info.resolution = float("nan")
    assert not map_pose_is_free(grid, 0.0, 0.0)


def test_asset_tree_digest_changes_for_name_or_bytes(tmp_path: Path) -> None:
    first = tmp_path / "one"
    second = tmp_path / "two"
    first.mkdir()
    second.mkdir()
    (first / "model.sdf").write_text("robot")
    (second / "model.sdf").write_text("robot")
    assert sha256_tree(first) == sha256_tree(second)
    (second / "model.sdf").rename(second / "different.sdf")
    assert sha256_tree(first) != sha256_tree(second)
    (second / "different.sdf").rename(second / "model.sdf")
    (second / "model.sdf").write_text("changed robot")
    assert sha256_tree(first) != sha256_tree(second)


def _asset_args(tmp_path: Path) -> argparse.Namespace:
    map_path = tmp_path / "map.yaml"
    map_path.write_text("image: map.pgm\n")
    (tmp_path / "map.pgm").write_bytes(b"PGM")
    for name in ("world.sdf", "rendered.sdf", "launch.py"):
        (tmp_path / name).write_text(name)
    params = tmp_path / "controller.yaml"
    params.write_text(yaml.safe_dump({"controller_server": {"ros__parameters": {
        "FollowPath": {"plugin": "nav2_mppi_controller::MPPIController", "vx_max": 0.5},
    }}}))
    shares = []
    for name in ("sim", "description"):
        share = tmp_path / name
        share.mkdir()
        (share / "package.xml").write_text(
            f"<package><name>tb4_{name}</name><version>1.2.0</version></package>"
        )
        shares.append(share)
    (shares[0] / "configs").mkdir()
    (shares[0] / "configs" / "tb4_bridge.yaml").write_text(
        "- ros_topic_name: cmd_vel\n  ros_type_name: geometry_msgs/msg/Twist\n"
    )
    return argparse.Namespace(
        map=map_path, world=tmp_path / "world.sdf", rendered_world=tmp_path / "rendered.sdf",
        launch=tmp_path / "launch.py", params=params, sim_share=shares[0],
        description_share=shares[1], start_x=0.0, start_y=0.0, start_yaw=0.0,
    )


def test_sut_digest_is_separate_from_stable_target_assets(tmp_path: Path, monkeypatch) -> None:
    args = _asset_args(tmp_path)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "no-fuel")
    monkeypatch.setenv("GZ_PARTITION", "one")
    baseline = asset_manifest(args)
    params = yaml.safe_load(args.params.read_text())
    params["controller_server"]["ros__parameters"]["FollowPath"]["vx_max"] = 0.2
    args.params.write_text(yaml.safe_dump(params))
    monkeypatch.setenv("GZ_PARTITION", "two")
    candidate = asset_manifest(args)
    assert baseline["assets"] == candidate["assets"]
    assert baseline["params_sha256"] != candidate["params_sha256"]
    assert candidate["params_sha256"] == sha256_file(args.params)
    assert baseline["world_partition"] != candidate["world_partition"]
    assert candidate["controller_expected"]["vx_max"] == 0.2
    assert candidate["packages"] == {"tb4_sim": "1.2.0", "tb4_description": "1.2.0"}


@pytest.mark.parametrize("speed", [True, "0.5", float("inf"), -0.5])
def test_sut_velocity_is_validated_before_ros_imports(tmp_path: Path, speed) -> None:
    args = _asset_args(tmp_path)
    data = yaml.safe_load(args.params.read_text())
    data["controller_server"]["ros__parameters"]["FollowPath"]["vx_max"] = speed
    args.params.write_text(yaml.safe_dump(data))
    with pytest.raises(ValueError, match="finite positive"):
        asset_manifest(args)


def test_invalid_cli_pose_persists_infrastructure_evidence(tmp_path: Path, monkeypatch) -> None:
    output = tmp_path / "result.gazebo.json"
    monkeypatch.setattr("sys.argv", [
        "readiness", "--start-x", "nan", "--start-y", "0", "--start-yaw", "0",
        "--goal-x", "5", "--goal-y", "0", "--map", "absent", "--world", "absent",
        "--rendered-world", "absent", "--params", "absent", "--launch", "absent",
        "--sim-share", "absent", "--description-share", "absent", "--output", str(output),
    ])
    assert main() == 3
    evidence = json.loads(output.read_text())
    assert evidence["status"] == "ERROR"
    assert "finite" in evidence["error"]


def test_cleanup_does_not_signal_recycled_pid_or_zombie(monkeypatch) -> None:
    signaled = []
    monkeypatch.setattr(gazebo_cleanup, "_identity", lambda pid: {
        123: ("new-start", "S"), 456: ("old-start", "Z"), 789: ("old-start", "S"),
    }.get(pid))
    monkeypatch.setattr(gazebo_cleanup.os, "kill", lambda pid, sig: signaled.append((pid, sig)))
    gazebo_cleanup._signal(
        {123: ("old-start", "S"), 456: ("old-start", "S"), 789: ("old-start", "S")},
        signal.SIGTERM,
    )
    assert signaled == [(789, signal.SIGTERM)]


def test_cleanup_rescans_for_detached_descendants_and_verifies_exit(monkeypatch) -> None:
    snapshots = iter([
        {12: ("one", "S")},
        {12: ("one", "S"), 34: ("two", "S")},
        {34: ("two", "S")},
        {},
    ])
    signals = []
    monkeypatch.setattr(gazebo_cleanup, "_owned", lambda partition: next(snapshots))
    monkeypatch.setattr(gazebo_cleanup, "_signal", lambda owned, sig: signals.extend(
        (pid, sig) for pid in owned
    ))
    monkeypatch.setattr(gazebo_cleanup.time, "sleep", lambda duration: None)
    result = gazebo_cleanup.stop_owned_gazebo("robotci-robotci-gazebo.unique")
    assert signals == [(12, signal.SIGTERM), (34, signal.SIGTERM)]
    assert result["process_groups_stopped"] is True
    assert result["processes_seen"] == [12, 34]


def test_cleanup_rejects_global_or_missing_partition() -> None:
    with pytest.raises(ValueError, match="per-attempt"):
        gazebo_cleanup.stop_owned_gazebo("default")


def test_cleanup_runs_even_when_readiness_json_is_truncated(tmp_path: Path, monkeypatch) -> None:
    output = tmp_path / "route.gazebo.json"
    output.write_text('{"status": "REA')
    calls = []
    monkeypatch.setattr("sys.argv", ["cleanup", "--output", str(output)])
    monkeypatch.setenv("GZ_PARTITION", "robotci-robotci-gazebo.test")

    def stop(partition):
        calls.append(partition)
        return {"process_groups_stopped": True, "survivors": []}

    monkeypatch.setattr(gazebo_cleanup, "stop_owned_gazebo", stop)
    assert gazebo_cleanup.main() == 3
    evidence = json.loads(output.read_text())
    assert calls == ["robotci-robotci-gazebo.test"]
    assert evidence["cleanup"]["process_groups_stopped"] is True
    assert evidence["status"] == "ERROR"
    assert "invalid readiness evidence" in evidence["error"]


@pytest.mark.skipif(os.name != "posix" or shutil.which("timeout") is None,
                    reason="Linux timeout/proc process ownership is required")
def test_cleanup_preserves_timeout_parent_and_kills_owned_detached_child(tmp_path: Path) -> None:
    if int(Path("/proc/self/stat").read_text().split(" ", 1)[0]) != os.getpid():
        pytest.skip("mounted /proc exposes a different PID namespace")
    partition = f"robotci-robotci-gazebo.{uuid.uuid4().hex}"
    environment = dict(os.environ, GZ_PARTITION=partition)
    child = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        env=environment, start_new_session=True,
    )
    output = tmp_path / "cleanup.json"
    output.write_text('{"schema_version": 1, "kind": "gazebo_runtime", "status": "READY"}')
    root = Path(__file__).resolve().parents[1]
    try:
        completed = subprocess.run(
            ["timeout", "--foreground", "10s", sys.executable, "-S", "-B", "-m",
             "robotci.ros.gazebo_cleanup", "--output", str(output)],
            cwd=root, env=environment, capture_output=True, text=True, timeout=12, check=False,
        )
        assert completed.returncode == 0, completed.stderr
        assert child.wait(timeout=2) == -signal.SIGTERM
        evidence = json.loads(output.read_text())
        assert evidence["cleanup"]["process_groups_stopped"] is True
        assert child.pid in evidence["cleanup"]["processes_seen"]
    finally:
        if child.poll() is None:
            child.kill()
        child.wait(timeout=2)
