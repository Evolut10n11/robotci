from __future__ import annotations

import copy
import importlib.util
import json
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from robotci.metrics import NavigationMetrics
from robotci.replay import ReplayRecorder, write_replay
from robotci.reproducibility import build_robotci_source_fingerprint
from robotci.results import Pose2D

SPEC = importlib.util.spec_from_file_location(
    "gazebo_acceptance", Path(__file__).parents[1] / "scripts/gazebo_acceptance.py"
)
assert SPEC is not None and SPEC.loader is not None
experiment = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(experiment)


@pytest.fixture
def subject() -> bytes:
    return b"""# Keep original bytes for restoration.
controller_server:
  ros__parameters:
    controller_frequency: 20.0
    FollowPath:
      plugin: nav2_mppi_controller::MPPIController
      vx_max: 0.5
      vy_max: 0.0
"""


def test_intervention_changes_one_semantic_parameter(subject: bytes) -> None:
    original = yaml.safe_load(subject)
    candidate = yaml.safe_load(experiment.candidate_parameters(subject))
    candidate["controller_server"]["ros__parameters"]["FollowPath"]["vx_max"] = 0.5
    assert candidate == original


@pytest.mark.parametrize("velocity", ["false", "0.2", ".nan", "'.5'"])
def test_intervention_rejects_unknown_baseline(subject: bytes, velocity: str) -> None:
    changed = subject.replace(b"vx_max: 0.5", f"vx_max: {velocity}".encode())
    with pytest.raises(experiment.AcceptanceError, match="vx_max"):
        experiment.candidate_parameters(changed)


def test_intervention_requires_real_mppi_controller(subject: bytes) -> None:
    changed = subject.replace(b"nav2_mppi_controller::MPPIController", b"other::Controller")
    with pytest.raises(experiment.AcceptanceError, match="MPPI"):
        experiment.candidate_parameters(changed)


@pytest.mark.parametrize("failure", [RuntimeError("runtime failed"), KeyboardInterrupt()])
def test_failed_candidate_restores_exact_subject(
    subject: bytes, tmp_path: Path, failure: BaseException
) -> None:
    params = tmp_path / "controller.yaml"
    params.write_bytes(subject)
    candidate = experiment.candidate_parameters(subject)
    with pytest.raises(type(failure)):
        with experiment.changed_subject(params, subject, candidate):
            assert params.read_bytes() == candidate
            raise failure
    assert params.read_bytes() == subject


def test_mid_run_subject_change_is_rejected_and_restored(subject: bytes, tmp_path: Path) -> None:
    params = tmp_path / "controller.yaml"
    params.write_bytes(subject)
    with pytest.raises(experiment.AcceptanceError, match="during"):
        with experiment.changed_subject(params, subject, experiment.candidate_parameters(subject)):
            params.write_text("untracked controller update")
    assert params.read_bytes() == subject


def test_failed_real_runtime_is_preserved_as_incomplete_evidence(
    subject: bytes, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    params = tmp_path / "controller.yaml"
    params.write_bytes(subject)
    config = tmp_path / "robotci.yaml"
    config.write_text("version: 1\n")
    adapter = tmp_path / "adapter.sh"
    adapter.write_text("#!/bin/bash\nexit 3\n")
    output = tmp_path / "evidence"
    commands = []

    def failed_runtime(command, **options):
        commands.append((command, options))
        return subprocess.CompletedProcess(command, returncode=3)

    monkeypatch.setattr(experiment, "run_runtime_process", failed_runtime)
    assert experiment.run_experiment(
        config=config, params=params, output=output, adapter=adapter
    ) == 3
    assert params.read_bytes() == subject
    manifest = json.loads((output / "experiment.json").read_text())
    assert manifest["status"] == "INCOMPLETE"
    assert manifest["runs"] == []
    assert manifest["duration_regression_detected"] is False
    assert manifest["subject_restored"] is True
    assert manifest["external_participants"] == 0
    assert commands[0][0][2] == "robotci.bootstrap"
    assert commands[0][1]["env"]["ROBOTCI_GAZEBO_PARAMS_FILE"] == str(params)
    # Existing evidence cannot be erased by an accidental rerun.
    with pytest.raises(experiment.AcceptanceError, match="previous attempts"):
        experiment.run_experiment(config=config, params=params, output=output, adapter=adapter)


def test_external_target_keeps_actual_harness_fingerprint_stable(
    subject: bytes, tmp_path: Path
) -> None:
    checkout = tmp_path / "checkout"
    package = checkout / "robotci"
    package.mkdir(parents=True)
    (package / "runner.py").write_text("VALUE = 1\n")
    scripts = checkout / "scripts"
    scripts.mkdir()
    adapter = scripts / "run_gazebo_attempt.sh"
    adapter.write_text("exit 0\n")
    # Match the workflow layout: actual executable/SUT input is outside ROOT;
    # copies inside artifacts use data suffixes, including the launch source.
    external = tmp_path / "runner-temp" / "robotci-gazebo-target"
    external.mkdir(parents=True)
    launch = external / "tb4_simulation_launch.py"
    launch.write_text("LAUNCH_VERSION = 1\n")
    params = external / "controller.yaml"
    params.write_bytes(subject)
    archive = checkout / "artifacts" / "target"
    archive.mkdir(parents=True)
    (archive / "tb4_simulation_launch.py.txt").write_bytes(launch.read_bytes())

    def harness() -> str:
        return build_robotci_source_fingerprint(
            package, runtime_root=checkout, attempt_script=adapter,
            attempt_script_identity=str(adapter),
        )

    before = harness()
    original_launch_digest = experiment.digest(launch.read_bytes())
    results = checkout / "artifacts" / "gazebo-acceptance" / "baseline-1" / "results"
    results.mkdir(parents=True)
    (results / "depot_route.json").write_text('{"kind": "synthetic-unit-test-output"}')
    (results / "depot_route.gazebo.json").write_text('{"kind": "synthetic-unit-test-target"}')
    params.write_bytes(experiment.candidate_parameters(subject))
    (archive / "controller.candidate.yaml").write_bytes(params.read_bytes())
    assert harness() == before
    # Separate target provenance still detects edits to the actual launch bytes.
    launch.write_text("LAUNCH_VERSION = 2\n")
    assert harness() == before
    assert experiment.digest(launch.read_bytes()) != original_launch_digest


@pytest.fixture
def provenance(subject: bytes) -> dict:
    return {
        "schema_version": 1, "kind": "gazebo_runtime", "status": "READY",
        "cleanup": {"process_groups_stopped": True, "survivors": []},
        "checks": {key: True for key in (
            "clock_progressing", "scan_received", "odom_received", "start_pose_verified",
            "physical_start_verified", "map_footprints_free", "required_tf",
            "nav2_active", "navigate_to_pose", "controller_stable", "cmd_vel_type_verified",
            "benchmark_preset_verified", "benchmark_preset_stable",
        )},
        "controller": {"plugin": experiment.MPPI_PLUGIN, "vx_max": 0.5},
        "controller_after": {"plugin": experiment.MPPI_PLUGIN, "vx_max": 0.5},
        "params_sha256": experiment.digest(subject),
        "params_sha256_after": experiment.digest(subject),
        "benchmark_preset": copy.deepcopy(experiment.BENCHMARK_PRESET),
        "benchmark_preset_after": copy.deepcopy(experiment.BENCHMARK_PRESET),
        "benchmark_preset_expected": copy.deepcopy(experiment.BENCHMARK_PRESET),
        "assets": {key: "sha256:" + "a" * 64 for key in (
            "map_yaml", "map_image", "world", "rendered_world", "launch",
            "tb4_sim_tree", "tb4_description_tree", "bridge_config",
        )},
        "packages": {"ros-jazzy-nav2-minimal-tb4-sim": "synthetic-unit-test-version"},
        "command_velocity_type": "geometry_msgs/msg/Twist",
        "stamped_cmd_vel": {key: False for key in (
            "controller_server", "behavior_server", "velocity_smoother", "collision_monitor",
        )},
    }


@pytest.mark.parametrize("mutation, message", [
    (lambda value: value.update(schema_version=True), "schema"),
    (lambda value: value.update(status="STARTED"), "readiness"),
    (lambda value: value["cleanup"].update(process_groups_stopped=False), "cleanup"),
    (lambda value: value["checks"].update(start_pose_verified=1), "start_pose"),
    (lambda value: value["controller"].update(vx_max=0.2), "read-back"),
    (lambda value: value.update(params_sha256="sha256:" + "b" * 64), "subject"),
    (lambda value: value["controller_after"].update(vx_max=0.2), "during navigation"),
    (lambda value: value.update(params_sha256_after="sha256:" + "b" * 64), "during navigation"),
    (lambda value: value["assets"].pop("world"), "target asset"),
    (lambda value: value["assets"].pop("launch"), "target asset"),
    (lambda value: value["assets"].pop("bridge_config"), "target asset"),
    (lambda value: value["assets"].update(world="unknown"), "digest"),
    (lambda value: value.update(packages={}), "packages"),
    (lambda value: value["stamped_cmd_vel"].update(controller_server=True), "message type"),
    (lambda value: value["benchmark_preset"].update(regenerate_noises=True), "preset differs"),
    (lambda value: value["benchmark_preset"].update(stateful=0), "preset differs"),
    (lambda value: value["benchmark_preset_after"].update(xy_goal_tolerance=0.25),
     "preset differs"),
    (lambda value: value["benchmark_preset_expected"].pop("visualize"), "complete fixed"),
])
def test_unverified_target_cannot_be_accepted(
    provenance: dict, subject: bytes, mutation, message: str
) -> None:
    mutation(provenance)
    with pytest.raises(experiment.AcceptanceError, match=message):
        experiment.validate_target(
            provenance, expected_digest=experiment.digest(subject), expected_velocity=0.5
        )


def test_sut_change_is_separate_from_fixed_target_identity(
    provenance: dict, subject: bytes
) -> None:
    baseline = experiment.validate_target(
        provenance, expected_digest=experiment.digest(subject), expected_velocity=0.5
    )
    candidate = copy.deepcopy(provenance)
    changed = experiment.candidate_parameters(subject)
    candidate["controller"]["vx_max"] = 0.2
    candidate["controller_after"]["vx_max"] = 0.2
    candidate["params_sha256"] = experiment.digest(changed)
    candidate["params_sha256_after"] = experiment.digest(changed)
    assert baseline == experiment.validate_target(
        candidate, expected_digest=experiment.digest(changed), expected_velocity=0.2
    )


@pytest.mark.parametrize("status, metric, expected, detected", [
    ("PASS", None, "COMPLETED_WITHOUT_DETECTED_SLOWDOWN", False),
    ("REGRESSION", "recoveries", "COMPLETED_OTHER_REGRESSION", False),
    ("REGRESSION", "duration_sec", "COMPLETED_DURATION_REGRESSION", True),
])
def test_gate_claim_matches_actual_intervention_findings(
    status: str, metric: str | None, expected: str, detected: bool
) -> None:
    report = {"status": status, "scenarios": [
        {"findings": [] if metric is None else [{"metric": metric}]}
    ]}
    assert experiment.measurement_outcome(report) == (expected, detected)


def test_whole_series_uses_real_artifact_validation_and_gates(
    provenance: dict, subject: bytes, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Synthetic runtime only; actual suite/replay validation, capture, gates execute."""
    fixture = Path(__file__).parent / "fixtures/gate-suite/pass"
    params = tmp_path / "controller.yaml"
    params.write_bytes(subject)
    config = tmp_path / "robotci.yaml"
    config.write_text("version: 1\n")
    adapter = tmp_path / "adapter.sh"
    adapter.write_text("#!/bin/bash\nexit 0\n")
    output = tmp_path / "evidence"
    observed = []

    def synthetic_runtime(command, **options):
        suite_path = Path(command[command.index("--output") + 1])
        name = suite_path.parent.name
        observed.append(name)
        shutil.copytree(fixture, suite_path.parent)
        suite = json.loads(suite_path.read_text())
        result_path = suite_path.parent / suite["scenarios"][0]["result_file"]
        result = json.loads(result_path.read_text())
        duration = 25.0 if name == "candidate" else 10.5
        suite["scenarios"][0]["duration_sec"] = duration
        result["duration_sec"] = duration
        suite_path.write_text(json.dumps(suite))
        result_path.write_text(json.dumps(result))
        recorder = ReplayRecorder(
            scenario=result["scenario"], start=Pose2D(**result["start"]),
            goal=Pose2D(**result["goal"]), started_at=0.0,
        )
        for index in range(20):
            recorder.record(x=index * 0.9 / 19, y=0.0, yaw=0.0, now=index * duration / 20)
        write_replay(recorder.build(
            status="PASS", duration_sec=duration, metrics=NavigationMetrics(**result["metrics"]),
            navigation_result="SUCCEEDED",
        ), result_path.with_suffix(".replay.json"))
        target = copy.deepcopy(provenance)
        speed = 0.2 if name == "candidate" else 0.5
        target["controller"]["vx_max"] = speed
        target["controller_after"]["vx_max"] = speed
        target["params_sha256"] = experiment.digest(params.read_bytes())
        target["params_sha256_after"] = target["params_sha256"]
        target["world_partition"] = "synthetic-unit-test-" + name
        result_path.with_suffix(".gazebo.json").write_text(json.dumps(target))
        return subprocess.CompletedProcess(command, returncode=0)

    monkeypatch.setattr(experiment, "run_runtime_process", synthetic_runtime)
    assert experiment.run_experiment(
        config=config, params=params, output=output, adapter=adapter,
        require_duration_regression=True,
    ) == 0
    assert observed == [
        "warmup", "baseline-1", "baseline-2", "baseline-3", "baseline-4", "baseline-5",
        "control", "candidate", "restored-control",
    ]
    manifest = json.loads((output / "experiment.json").read_text())
    assert manifest["status"] == "COMPLETED_DURATION_REGRESSION"
    assert len(manifest["unchanged_pair_gates"]) == 20
    assert all(item["status"] == "PASS" for item in manifest["unchanged_pair_gates"])
    assert manifest["baseline_duration_sec"]["median"] == 10.5
    assert manifest["subject_restored"] is True
    assert params.read_bytes() == subject
    for name in ("control-gate", "candidate-gate", "restored-control-gate"):
        for extension in ("json", "md", "xml"):
            assert (output / f"{name}.{extension}").is_file()
    captured = output / "baselines/gazebo-known-good/results/route.replay.json"
    assert captured.is_file()
