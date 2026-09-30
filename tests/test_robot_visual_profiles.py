from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from robotci import runner
from robotci.baselines import capture_baseline
from robotci.config import ConfigError, load_config
from robotci.metrics import NavigationMetrics
from robotci.replay import ReplayRecorder, default_replay_path, write_replay
from robotci.reproducibility import build_suite_plan_fingerprint, validate_suite_execution
from robotci.results import Pose2D
from robotci.viewer import ViewerError, demo_replay, load_replay, validate_replay

FIXTURE = Path(__file__).parent / "fixtures/gate-suite/baseline"


def _config(path: Path, robot: object = None) -> Path:
    data = {
        "version": 1,
        "runtime": "native",
        "scenarios": [{
            "name": "route",
            "map_id": "nav2-loopback",
            "start": {"x": 0, "y": 0},
            "goal": {"x": 1, "y": 0},
            "timeout_sec": 30,
        }],
    }
    if robot is not None:
        data["robot"] = robot
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _record(result: dict, *, profile: str = "rover") -> dict:
    recorder = ReplayRecorder(
        scenario=result["scenario"],
        start=Pose2D(**result["start"]),
        goal=Pose2D(**result["goal"]),
        started_at=100,
        visual_profile=profile,
    )
    recorder.record(x=1, y=0, yaw=0, now=105)
    return recorder.build(
        status=result["status"],
        duration_sec=result["duration_sec"],
        metrics=NavigationMetrics(**result["metrics"]),
        navigation_result=result["navigation_result"],
    )


def _artifacts(root: Path) -> tuple[Path, Path]:
    shutil.copytree(FIXTURE, root)
    result_path = root / "results/route.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    replay_path = write_replay(_record(result), default_replay_path(result_path))
    return result_path, replay_path


@pytest.mark.parametrize("profile", ["rover", "quadruped", "humanoid"])
def test_visual_profile_config_and_recording_are_presentation_only(
    tmp_path: Path, profile: str,
) -> None:
    path = _config(tmp_path / "robotci.yaml")
    original = load_config(path)
    _config(path, {"visual_profile": profile})
    configured = load_config(path)
    assert configured.robot.visual_profile == profile
    assert configured.scenarios == original.scenarios
    assert build_suite_plan_fingerprint(configured, timeout_sec=None) == (
        build_suite_plan_fingerprint(original, timeout_sec=None)
    )
    result = json.loads((FIXTURE / "results/route.json").read_text(encoding="utf-8"))
    payload = _record(result, profile=profile)
    saved = load_replay(write_replay(payload, tmp_path / "recording.json"))
    assert saved["robot"] == {"type": "generic_mobile_base", "visual_profile": profile}
    assert saved["samples"] == _record(result)["samples"]
    assert saved["metrics"] == _record(result)["metrics"]


def test_legacy_config_and_replay_keep_default_rover_without_mutating_input(tmp_path: Path) -> None:
    config = load_config(_config(tmp_path / "robotci.yaml"))
    assert config.robot.visual_profile == "rover"
    replay = demo_replay()
    replay["robot"] = {"type": "external_custom_base"}
    assert validate_replay(replay)["robot"] == {"type": "external_custom_base"}


def test_replay_reader_keeps_working_without_installed_dependencies() -> None:
    subprocess.run(
        [
            sys.executable, "-S", "-c",
            "from robotci.viewer import demo_replay, validate_replay; "
            "replay = demo_replay(); replay['robot']['visual_profile'] = 'quadruped'; "
            "validate_replay(replay)",
        ],
        cwd=Path(__file__).parents[1],
        check=True,
    )


@pytest.mark.parametrize("profile", ["unknown", "", " rover ", None, True, [], {}])
def test_invalid_visual_profile_is_rejected_at_config_and_replay_boundaries(
    tmp_path: Path, profile: object,
) -> None:
    with pytest.raises(ConfigError, match="robot.visual_profile"):
        load_config(_config(tmp_path / "robotci.yaml", {"visual_profile": profile}))
    replay = demo_replay()
    replay["robot"]["visual_profile"] = profile
    with pytest.raises(ViewerError, match="robot.visual_profile"):
        validate_replay(replay)


@pytest.mark.parametrize("robot", [[], "quadruped", {"type": "quadruped"}])
def test_config_robot_block_is_strict(tmp_path: Path, robot: object) -> None:
    with pytest.raises(ConfigError, match="config.robot"):
        load_config(_config(tmp_path / "robotci.yaml", robot))


@pytest.mark.parametrize("entrypoint", ["scenario", "suite"])
@pytest.mark.parametrize("runtime", ["native", "docker"])
def test_runner_persists_configured_profile_for_single_and_suite_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, entrypoint: str, runtime: str,
) -> None:
    config_path = _config(tmp_path / "robotci.yaml", {"visual_profile": "quadruped"})
    result = json.loads((FIXTURE / "results/route.json").read_text(encoding="utf-8"))
    execution = validate_suite_execution(
        json.loads((FIXTURE / "suite-result.json").read_text(encoding="utf-8"))
    )

    def fake_runtime(_root, _scenario, output, _timeout, *_args, **_kwargs):
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result), encoding="utf-8")
        write_replay(_record(result), default_replay_path(output))
        return 0

    monkeypatch.setattr(runner, "_find_runtime_root", lambda _root: tmp_path)
    monkeypatch.setattr(runner, "select_runtime", lambda _requested: runtime)
    monkeypatch.setattr(runner, "capture_suite_execution", lambda **_kwargs: execution)
    monkeypatch.setattr(runner, "_run_native", fake_runtime)
    monkeypatch.setattr(runner, "_run_docker", fake_runtime)
    if entrypoint == "scenario":
        code, selected, result_path = runner.run_scenario(
            scenario="route", config_path=config_path, project_root=tmp_path,
        )
    else:
        code, selected, suite_path = runner.run_suite(
            config_path=config_path, project_root=tmp_path,
        )
        result_path = suite_path.parent / "results/route.json"
        captured = capture_baseline("visual", suite_path, store_root=tmp_path / "baselines")
        assert load_replay(captured.path / "results/route.replay.json")["robot"] == {
            "type": "generic_mobile_base", "visual_profile": "quadruped",
        }
    assert (code, selected) == (0, runtime)
    assert json.loads(result_path.read_text(encoding="utf-8")) == result
    saved = load_replay(default_replay_path(result_path))
    assert saved["robot"] == {"type": "generic_mobile_base", "visual_profile": "quadruped"}
    assert saved["samples"] == _record(result)["samples"]
    assert saved["metrics"] == _record(result)["metrics"]


@pytest.mark.parametrize("status", ["PASS", "FAIL", "TIMEOUT", "INFRA_ERROR"])
def test_annotation_preserves_all_result_statuses_and_events(tmp_path: Path, status: str) -> None:
    result_path, replay_path = _artifacts(tmp_path / "run")
    result = json.loads(result_path.read_text(encoding="utf-8"))
    if status != "PASS":
        result.update(status=status, navigation_result="ABORTED", reason_code="navigation_aborted")
    result_path.write_text(json.dumps(result), encoding="utf-8")
    write_replay(_record(result), replay_path)
    original_result = result_path.read_bytes()
    original_replay = load_replay(replay_path)

    runner._annotate_replay_visual_profile(result_path, "humanoid")

    saved = load_replay(replay_path)
    assert result_path.read_bytes() == original_result
    assert saved["robot"]["visual_profile"] == "humanoid"
    assert {key: value for key, value in saved.items() if key != "robot"} == {
        key: value for key, value in original_replay.items() if key != "robot"
    }


def test_missing_replay_is_not_fabricated(tmp_path: Path) -> None:
    result_path, replay_path = _artifacts(tmp_path / "run")
    replay_path.unlink()
    original = result_path.read_bytes()

    runner._annotate_replay_visual_profile(result_path, "quadruped")

    assert not replay_path.exists()
    assert result_path.read_bytes() == original


@pytest.mark.parametrize("corruption", ["malformed", "mismatched"])
def test_invalid_replay_stays_unavailable_and_result_is_unchanged(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, corruption: str,
) -> None:
    result_path, replay_path = _artifacts(tmp_path / "run")
    if corruption == "malformed":
        replay_path.write_text("{broken", encoding="utf-8")
    else:
        payload = load_replay(replay_path)
        payload["metrics"]["path_length_m"] += 1
        write_replay(payload, replay_path)
    original_result, original_replay = result_path.read_bytes(), replay_path.read_bytes()

    runner._annotate_replay_visual_profile(result_path, "quadruped")

    assert result_path.read_bytes() == original_result
    assert replay_path.read_bytes() == original_replay
    assert "Navigation result is unchanged" in caplog.text


@pytest.mark.parametrize("failure", ["probe", "replace"])
def test_failed_annotation_keeps_valid_original_and_warns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture,
    failure: str,
) -> None:
    result_path, replay_path = _artifacts(tmp_path / "run")
    original_result, original_replay = result_path.read_bytes(), replay_path.read_bytes()

    def deny_replace(_source, _destination):
        raise PermissionError("file is in use")

    if failure == "replace":
        monkeypatch.setattr(runner.os, "replace", deny_replace)
    else:
        original_is_file = Path.is_file

        def deny_replay_probe(path):
            if path == replay_path:
                raise PermissionError("file is in use")
            return original_is_file(path)

        monkeypatch.setattr(Path, "is_file", deny_replay_probe)

    runner._annotate_replay_visual_profile(result_path, "quadruped")

    assert result_path.read_bytes() == original_result
    assert replay_path.read_bytes() == original_replay
    assert not list(replay_path.parent.glob(".robotci-replay-*"))
    assert "file is in use" in caplog.text
    assert "Navigation result is unchanged" in caplog.text
