"""Synthetic unit fixtures for the post-run verifier, not simulator evidence."""
from __future__ import annotations

import json
import runpy
import subprocess
from dataclasses import asdict
from pathlib import Path

import pytest

from robotci.reproducibility import (
    RuntimePackage,
    build_runtime_environment,
    build_suite_execution_identity,
)
from robotci.results import Pose2D, build_scenario_task
from robotci.viewer import demo_replay

VERIFIER = runpy.run_path(
    str(Path(__file__).resolve().parents[1] / "scripts" / "verify_postrun_acceptance.py")
)


def _fixture(root: Path, runtime: str = "native") -> Path:
    replay = demo_replay()
    start = Pose2D(x=0.0, y=0.0, yaw=0.0)
    goal = Pose2D(x=5.0, y=3.0, yaw=0.0)
    scenario = replay["scenario"]
    environment = build_runtime_environment(
        os_id="ubuntu", os_version="24.04", architecture="x86_64",
        python_version="3.12.3", ros_distro="jazzy", robotci_build="sha256:" + "2" * 64,
        containerized=runtime == "docker",
        packages=(RuntimePackage(manager="python", name="robotci", version="0.1.0a1"),),
    )
    execution = build_suite_execution_identity(
        runtime=runtime, plan_fingerprint="sha256:" + "1" * 64, environment=environment,
    )
    result = {
        "schema_version": 2, "scenario": scenario, "status": "PASS", "duration_sec": 12.0,
        "navigation_result": "SUCCEEDED", "start": asdict(start), "goal": asdict(goal),
        "task": asdict(build_scenario_task(
            scenario=scenario, start=start, goal=goal, map_id="nav2-loopback",
        )),
        "metrics": {
            "path_length_m": 6.05, "distance_to_goal_m": 0.0, "stuck_events": 1,
            "feedback_samples": 10, "recoveries": 1,
        },
        "telemetry_quality": {
            "received_feedback_samples": 10, "valid_pose_samples": 10,
            "invalid_pose_samples": 0, "final_pose_valid": True,
        },
        "evidence_policy": {"goal_tolerance_m": 0.25, "min_feedback_samples": 1},
    }
    suite = {
        "schema_version": 1, "status": "PASS", "runtime": runtime,
        "execution": asdict(execution), "duration_sec": 12.0,
        "scenarios": [{
            "scenario": scenario, "status": "PASS", "duration_sec": 12.0,
            "result_file": "results/route.json",
        }],
    }
    (root / "results").mkdir(parents=True)
    (root / "results/route.json").write_text(json.dumps(result), encoding="utf-8")
    (root / "results/route.replay.json").write_text(json.dumps(replay), encoding="utf-8")
    path = root / "suite-result.json"
    path.write_text(json.dumps(suite), encoding="utf-8")
    return path


def _contents(root: Path) -> dict[str, bytes]:
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}


@pytest.mark.parametrize("runtime", ["native", "docker"])
def test_full_verifier_keeps_original_evidence_and_labels_controls(tmp_path, runtime) -> None:
    suite = _fixture(tmp_path / "source", runtime)
    before = _contents(suite.parent)
    report = VERIFIER["verify"](suite)
    assert report["status"] == "PASS"
    assert report["runtime"] == runtime
    assert report["scenario_count"] == 1
    assert len(report["checks"]) == 14
    assert report["synthetic_controls"] is True
    assert report["new_simulation_executed"] is False
    assert report["external_pilot_evidence"] is False
    assert report["browser_rendering_checked"] is False
    assert report["mcp_transport_checked"] is False
    assert _contents(suite.parent) == before
    assert not (suite.parent / ".robotci").exists()


def test_missing_suite_returns_failure_without_success_json(tmp_path, capsys) -> None:
    code = VERIFIER["main"](["--suite", str(tmp_path / "absent.json")])
    output = capsys.readouterr()
    assert code == 1
    assert output.out == ""
    assert "Post-run acceptance failed" in output.err


@pytest.mark.parametrize("change", ["missing_replay", "summary_duration", "missing_result"])
def test_incomplete_input_is_not_accepted_or_modified(tmp_path, capsys, change) -> None:
    suite = _fixture(tmp_path / "source")
    if change == "missing_replay":
        (suite.parent / "results/route.replay.json").unlink()
    elif change == "missing_result":
        (suite.parent / "results/route.json").unlink()
    else:
        data = json.loads(suite.read_text(encoding="utf-8"))
        data["scenarios"][0]["duration_sec"] += 1
        suite.write_text(json.dumps(data), encoding="utf-8")
    before = _contents(suite.parent)
    assert VERIFIER["main"](["--suite", str(suite)]) == 1
    assert capsys.readouterr().out == ""
    assert _contents(suite.parent) == before


def test_replay_symlink_outside_suite_is_refused(tmp_path, capsys) -> None:
    suite = _fixture(tmp_path / "source")
    replay = suite.parent / "results/route.replay.json"
    external = tmp_path / "private-replay.json"
    external.write_bytes(replay.read_bytes())
    replay.unlink()
    try:
        replay.symlink_to(external)
    except OSError:
        pytest.skip("symlink creation not permitted on this host")
    assert VERIFIER["main"](["--suite", str(suite)]) == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert "inside the suite directory" in output.err


def test_cli_timeout_is_not_reported_as_acceptance(tmp_path, monkeypatch, capsys) -> None:
    suite = _fixture(tmp_path / "source")
    before = _contents(suite.parent)

    def timed_out(*args, **kwargs):
        raise subprocess.TimeoutExpired("baseline", 30)

    monkeypatch.setitem(VERIFIER["verify"].__globals__, "_cli", timed_out)
    assert VERIFIER["main"](["--suite", str(suite)]) == 1
    assert capsys.readouterr().out == ""
    assert _contents(suite.parent) == before
