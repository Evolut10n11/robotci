"""Collect a real Gazebo controller experiment without changing gate policy.

Run with ROS 2 Jazzy sourced and the checked-in Gazebo adapter. This module has
no ROS imports; telemetry and target read-back are produced by the adapter.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import statistics
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

import yaml

from robotci.baselines import capture_baseline
from robotci.regression import RegressionPolicy
from robotci.replay import default_replay_path
from robotci.runtime_process import run_runtime_process
from robotci.suite_comparison import compare_suite_result_files
from robotci.suite_reporting import (
    suite_regression_report_payload,
    write_suite_regression_junit,
    write_suite_regression_markdown,
    write_suite_regression_report,
)
from robotci.suite_schema import load_suite_result
from robotci.viewer import load_replay
from robotci.viewer_session import replay_matches_result

ROOT = Path(__file__).resolve().parents[1]
BASELINE_REPETITIONS = 5
MPPI_PLUGIN = "nav2_mppi_controller::MPPIController"
SHIM_PLUGIN = "nav2_rotation_shim_controller::RotationShimController"
SUT_KEY = "controller_server.ros__parameters.FollowPath.vx_max"
BENCHMARK_PRESET = {
    "visualize": False,
    "regenerate_noises": False,
    "xy_goal_tolerance": 0.20,
    "yaw_goal_tolerance": 0.25,
    "stateful": True,
    "goal_angle_activation_distance": 0.20,
}


class AcceptanceError(ValueError):
    """The experiment is incomplete or its evidence is not trustworthy."""


def digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


def candidate_parameters(original: bytes) -> bytes:
    """Change one actual MPPI setting; reject a different baseline/controller."""
    try:
        document = yaml.safe_load(original)
        controller = document["controller_server"]["ros__parameters"]["FollowPath"]
        velocity = controller["vx_max"]
        if (controller.get("plugin") != SHIM_PLUGIN
                or controller.get("primary_controller") != MPPI_PLUGIN
                or controller.get("rotate_to_goal_heading") is not True):
            raise AcceptanceError("the baseline must use RotationShim with MPPI and goal rotation")
        if isinstance(velocity, bool) or not isinstance(velocity, int | float):
            raise AcceptanceError("baseline MPPI vx_max must be the numeric value 0.5")
        if velocity != 0.5:
            raise AcceptanceError("baseline MPPI vx_max must be 0.5 m/s")
    except (KeyError, TypeError, yaml.YAMLError) as exc:
        raise AcceptanceError("controller YAML has no valid MPPI FollowPath configuration") from exc
    candidate = copy.deepcopy(document)
    candidate["controller_server"]["ros__parameters"]["FollowPath"]["vx_max"] = 0.2
    return yaml.safe_dump(candidate, sort_keys=False).encode("utf-8")


@contextmanager
def changed_subject(path: Path, original: bytes, candidate: bytes) -> Iterator[None]:
    """Restore the exact initial bytes even when navigation or comparison fails."""
    if path.read_bytes() != original:
        raise AcceptanceError("controller file changed before the candidate intervention")
    try:
        path.write_bytes(candidate)
        yield
        if path.read_bytes() != candidate:
            raise AcceptanceError("controller file changed during the candidate run")
    finally:
        path.write_bytes(original)


def validate_target(
    value: object, *, expected_digest: str, expected_velocity: float
) -> dict[str, object]:
    """Return only target/harness inputs that must stay fixed between runs."""
    if not isinstance(value, dict) or type(value.get("schema_version")) is not int:
        raise AcceptanceError("missing Gazebo target manifest schema v1")
    if value["schema_version"] != 1:
        raise AcceptanceError("missing Gazebo target manifest schema v1")
    if value.get("kind") != "gazebo_runtime" or value.get("status") != "READY":
        raise AcceptanceError("Gazebo adapter did not record verified readiness")
    cleanup = value.get("cleanup")
    if not isinstance(cleanup, dict) or cleanup.get("process_groups_stopped") is not True:
        raise AcceptanceError("Gazebo adapter did not verify owned process cleanup")
    checks = value.get("checks")
    for name in (
        "clock_progressing", "scan_received", "odom_received", "start_pose_verified",
        "physical_start_verified", "map_footprints_free", "required_tf", "nav2_active",
        "navigate_to_pose", "controller_stable", "cmd_vel_type_verified",
        "benchmark_preset_verified", "benchmark_preset_stable",
        "behavior_tree_verified", "behavior_tree_stable",
    ):
        if not isinstance(checks, dict) or checks.get(name) is not True:
            raise AcceptanceError(f"Gazebo readiness evidence missing: {name}")
    controller = value.get("controller")
    if (not isinstance(controller, dict) or controller.get("plugin") != SHIM_PLUGIN
            or controller.get("primary_controller") != MPPI_PLUGIN
            or controller.get("rotate_to_goal_heading") is not True):
        raise AcceptanceError("runtime read-back did not confirm RotationShim/MPPI goal rotation")
    velocity = controller.get("vx_max")
    if (
        isinstance(velocity, bool)
        or not isinstance(velocity, int | float)
        or not math.isclose(velocity, expected_velocity, rel_tol=0, abs_tol=1e-9)
    ):
        raise AcceptanceError(f"runtime vx_max read-back must be {expected_velocity} m/s")
    if value.get("params_sha256") != expected_digest:
        raise AcceptanceError("adapter controller digest does not match the experiment subject")
    if value.get("params_sha256_after") != expected_digest:
        raise AcceptanceError("controller YAML digest changed during navigation")
    if value.get("controller_after") != controller:
        raise AcceptanceError("effective controller settings changed during navigation")
    for phase in ("benchmark_preset", "benchmark_preset_after", "benchmark_preset_expected"):
        preset = value.get(phase)
        if not isinstance(preset, dict) or preset.keys() != BENCHMARK_PRESET.keys():
            raise AcceptanceError(f"Gazebo manifest has no complete fixed {phase}")
        for name, expected in BENCHMARK_PRESET.items():
            observed = preset[name]
            if isinstance(expected, bool):
                valid = observed is expected
            else:
                valid = (
                    not isinstance(observed, bool)
                    and isinstance(observed, int | float)
                    and observed == expected
                )
            if not valid:
                raise AcceptanceError(f"fixed benchmark preset differs: {phase}.{name}")
    assets = value.get("assets")
    required_assets = {
        "map_yaml", "map_image", "world", "rendered_world", "launch",
        "tb4_sim_tree", "tb4_description_tree", "bridge_config",
        "behavior_tree",
    }
    if not isinstance(assets, dict) or not required_assets <= assets.keys():
        raise AcceptanceError("Gazebo manifest does not identify every required target asset")
    for name, fingerprint in assets.items():
        if (
            not isinstance(fingerprint, str)
            or len(fingerprint) != 71
            or not fingerprint.startswith("sha256:")
            or any(char not in "0123456789abcdef" for char in fingerprint[7:])
        ):
            raise AcceptanceError(f"invalid Gazebo asset digest: {name}")
    behavior = value.get("behavior_tree_expected")
    if not isinstance(behavior, dict) or behavior.keys() != {"path", "sha256"}:
        raise AcceptanceError("Gazebo manifest has no complete fixed behavior tree")
    behavior_path = behavior["path"]
    if (not isinstance(behavior_path, str) or not behavior_path
            or any(char in behavior_path for char in ("\n", "\r", "\0"))
            or not os.path.isabs(behavior_path)
            or os.path.normpath(behavior_path) != behavior_path):
        raise AcceptanceError("behavior tree path must be canonical and absolute")
    if behavior["sha256"] != assets["behavior_tree"]:
        raise AcceptanceError("behavior tree digest differs from the fixed target asset")
    if (value.get("behavior_tree") != behavior
            or value.get("behavior_tree_after") != behavior):
        raise AcceptanceError("effective behavior tree changed during navigation")
    packages = value.get("packages")
    if not isinstance(packages, dict) or not packages:
        raise AcceptanceError("Gazebo manifest does not identify installed target packages")
    command_type = value.get("command_velocity_type")
    supported = {"geometry_msgs/msg/Twist": False, "geometry_msgs/msg/TwistStamped": True}
    if not isinstance(command_type, str) or command_type not in supported:
        raise AcceptanceError("Gazebo manifest has no supported cmd_vel message type")
    velocity_flags = value.get("stamped_cmd_vel")
    for node in ("controller_server", "behavior_server", "velocity_smoother", "collision_monitor"):
        if (
            not isinstance(velocity_flags, dict)
            or velocity_flags.get(node) is not supported[command_type]
        ):
            raise AcceptanceError(f"effective {node} command message type differs from the bridge")
    return {"assets": assets, "packages": packages, "command_velocity_type": command_type,
            "stamped_cmd_vel": velocity_flags, "benchmark_preset": value["benchmark_preset"],
            "behavior_tree": behavior}


def measurement_outcome(candidate_report: dict[str, object]) -> tuple[str, bool]:
    """A completed gate alone cannot establish that the speed intervention was detected."""
    status = candidate_report.get("status")
    scenarios = candidate_report.get("scenarios", [])
    duration_detected = status == "REGRESSION" and any(
        finding.get("metric") == "duration_sec"
        for item in scenarios
        for finding in item.get("findings", [])
    )
    if duration_detected:
        return "COMPLETED_DURATION_REGRESSION", True
    if status == "REGRESSION":
        return "COMPLETED_OTHER_REGRESSION", False
    if status == "PASS":
        return "COMPLETED_WITHOUT_DETECTED_SLOWDOWN", False
    raise AcceptanceError("candidate gate has no completed PASS/REGRESSION verdict")


def _gate(baseline: Path, candidate: Path, output: Path) -> dict[str, object]:
    policy = RegressionPolicy()
    report = compare_suite_result_files(
        baseline_path=baseline, candidate_path=candidate, policy=policy
    )
    for extension, writer in (
        ("json", write_suite_regression_report),
        ("md", write_suite_regression_markdown),
    ):
        writer(
            output.with_suffix("." + extension), report=report, policy=policy,
            baseline_path=baseline, candidate_path=candidate,
        )
    write_suite_regression_junit(
        output.with_suffix(".xml"), report=report,
        baseline_path=baseline, candidate_path=candidate,
    )
    return suite_regression_report_payload(
        report=report, policy=policy, baseline_path=baseline, candidate_path=candidate
    )


def _validate_run(
    path: Path, *, subject_digest: str, velocity: float,
    stable_target: dict[str, object] | None,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    suite = load_suite_result(path)
    if suite.status != "PASS" or suite.runtime != "native":
        raise AcceptanceError(f"{path.parent.name}: native navigation did not complete with PASS")
    measured: list[dict[str, object]] = []
    for entry in suite.scenarios:
        sidecar = entry.result_path.with_suffix(".gazebo.json")
        target = json.loads(sidecar.read_text(encoding="utf-8"))
        identity = validate_target(
            target, expected_digest=subject_digest, expected_velocity=velocity
        )
        if stable_target is not None and identity != stable_target:
            raise AcceptanceError("Gazebo packages/assets changed during the measurement series")
        stable_target = identity
        replay = load_replay(default_replay_path(entry.result_path))
        replay_matches_result(replay, entry.result)
        result = json.loads(entry.result_path.read_text(encoding="utf-8"))
        measured.append({
            "scenario": entry.scenario, "duration_sec": entry.duration_sec,
            "metrics": result["metrics"], "telemetry_quality": result["telemetry_quality"],
            "target_manifest": str(sidecar), "replay": str(default_replay_path(entry.result_path)),
        })
    if stable_target is None:
        raise AcceptanceError("no scenario target evidence was produced")
    return stable_target, measured


def run_experiment(
    *, config: Path, params: Path, output: Path, adapter: Path,
    total_timeout: float = 1800, require_duration_regression: bool = False,
) -> int:
    if output.exists():
        raise AcceptanceError("use a new evidence directory; previous attempts must be preserved")
    original = params.read_bytes()
    candidate = candidate_parameters(original)
    output.mkdir(parents=True)
    (output / "subject.original.yaml").write_bytes(original)
    (output / "subject.candidate.yaml").write_bytes(candidate)
    (output / "acceptance.yaml").write_bytes(config.read_bytes())
    manifest: dict[str, object] = {
        "schema_version": 1, "kind": "gazebo_acceptance", "status": "RUNNING",
        "started_at": datetime.now(UTC).isoformat(), "external_participants": 0,
        "baseline_selection": "baseline-1, selected before data collection",
        "baseline_repetitions": BASELINE_REPETITIONS,
        "config_sha256": digest(config.read_bytes()),
        "adapter_sha256": digest(adapter.read_bytes()),
        "subject": {"key": SUT_KEY, "baseline": 0.5, "candidate": 0.2,
                    "baseline_sha256": digest(original), "candidate_sha256": digest(candidate)},
        "benchmark_preset": BENCHMARK_PRESET,
        "policy": {"duration_pct": 10, "path_pct": 10, "distance_m": 0.1,
                   "additional_stuck_events": 0, "additional_recoveries": 0},
        "runs": [], "unchanged_pair_gates": [], "duration_regression_detected": False,
    }
    deadline = time.monotonic() + total_timeout
    stable_target: dict[str, object] | None = None
    partitions: set[str] = set()
    baseline_paths: list[Path] = []
    environment = dict(os.environ)
    environment["ROBOTCI_ATTEMPT_SCRIPT"] = str(adapter.resolve())
    environment["ROBOTCI_GAZEBO_PARAMS_FILE"] = str(params.resolve())

    def save() -> None:
        _write_json(output / "experiment.json", manifest)

    def collect(name: str, subject: bytes, velocity: float) -> Path:
        nonlocal stable_target
        if params.read_bytes() != subject:
            raise AcceptanceError("controller subject changed before a run")
        if digest(config.read_bytes()) != manifest["config_sha256"]:
            raise AcceptanceError("scenario configuration changed during the experiment")
        if digest(adapter.read_bytes()) != manifest["adapter_sha256"]:
            raise AcceptanceError("Gazebo adapter changed during the experiment")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise AcceptanceError("experiment exceeded its total runtime budget")
        suite = output / name / "suite-result.json"
        manifest["active_run"] = name
        save()
        completed = run_runtime_process(
            [sys.executable, "-m", "robotci.bootstrap", "run", "--runtime", "native",
             "--config", str(config), "--output", str(suite)],
            cwd=ROOT, timeout=remaining, env=environment,
        )
        if completed.returncode != 0:
            raise AcceptanceError(f"{name}: robotci run exited {completed.returncode}")
        if params.read_bytes() != subject:
            raise AcceptanceError("controller subject changed during a run")
        stable_target, measured = _validate_run(
            suite, subject_digest=digest(subject), velocity=velocity,
            stable_target=stable_target,
        )
        for entry in load_suite_result(suite).scenarios:
            target = json.loads(entry.result_path.with_suffix(".gazebo.json").read_text())
            partition = target.get("world_partition")
            if not isinstance(partition, str) or not partition or partition in partitions:
                raise AcceptanceError("each run must use a fresh observed Gazebo partition")
            partitions.add(partition)
        manifest["target"] = stable_target
        manifest["runs"].append({"name": name, "suite": str(suite), "measurements": measured})
        save()
        return suite

    try:
        save()
        # Resolve Fuel downloads/caches through a real navigation run before
        # freezing the invariant target used for the measured baseline series.
        collect("warmup", original, 0.5)
        stable_target = None
        manifest["target_frozen_after_warmup"] = True
        for number in range(1, BASELINE_REPETITIONS + 1):
            baseline_paths.append(collect(f"baseline-{number}", original, 0.5))
        unstable: list[str] = []
        for baseline_index, baseline in enumerate(baseline_paths, start=1):
            for candidate_index, unchanged in enumerate(baseline_paths, start=1):
                if baseline_index == candidate_index:
                    continue
                name = f"baseline-{baseline_index}-vs-{candidate_index}"
                report = _gate(baseline, unchanged, output / "stability" / name)
                manifest["unchanged_pair_gates"].append({"name": name, "status": report["status"]})
                if report["status"] != "PASS":
                    unstable.append(name)
        save()
        if unstable:
            manifest["status"] = "UNCHANGED_BASELINES_UNSTABLE"
            manifest["error"] = "Default policy rejected unchanged pairs: " + ", ".join(unstable)
            return 1
        info = capture_baseline(
            "gazebo-known-good", baseline_paths[0], store_root=output / "baselines"
        )
        baseline = info.path / "suite-result.json"
        control = collect("control", original, 0.5)
        control_report = _gate(baseline, control, output / "control-gate")
        if control_report["status"] != "PASS":
            manifest["status"] = "UNCHANGED_CONTROL_REGRESSION"
            return 1
        with changed_subject(params, original, candidate):
            candidate_suite = collect("candidate", candidate, 0.2)
            candidate_report = _gate(baseline, candidate_suite, output / "candidate-gate")
            manifest["candidate_gate_status"] = candidate_report["status"]
            # Restoration/control is mandatory even when the candidate gate is PASS.
        restored = collect("restored-control", original, 0.5)
        restored_report = _gate(baseline, restored, output / "restored-control-gate")
        if restored_report["status"] != "PASS":
            manifest["status"] = "RESTORED_CONTROL_REGRESSION"
            return 1
        status, detected = measurement_outcome(candidate_report)
        manifest["status"] = status
        manifest["duration_regression_detected"] = detected
        return 0 if detected or not require_duration_regression else 1
    except (ValueError, OSError, subprocess.TimeoutExpired) as exc:
        manifest["status"] = "INCOMPLETE"
        manifest["error"] = f"{type(exc).__name__}: {exc}"
        return 3
    except BaseException:
        manifest["status"] = "INTERRUPTED"
        raise
    finally:
        params.write_bytes(original)
        manifest["subject_restored"] = params.read_bytes() == original
        manifest["finished_at"] = datetime.now(UTC).isoformat()
        manifest.pop("active_run", None)
        baselines = [item for item in manifest["runs"] if item["name"].startswith("baseline-")]
        durations = [item["measurements"][0]["duration_sec"] for item in baselines]
        if durations:
            manifest["baseline_duration_sec"] = {
                "min": min(durations), "max": max(durations), "median": statistics.median(durations)
            }
            path_lengths = [item["measurements"][0]["metrics"]["path_length_m"]
                            for item in baselines]
            manifest["baseline_path_length_m"] = {
                "min": min(path_lengths), "max": max(path_lengths),
                "median": statistics.median(path_lengths),
            }
        save()
        print(json.dumps({key: manifest[key] for key in (
            "status", "duration_regression_detected", "subject_restored"
        )}, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "examples/nav2-gazebo/robotci.yaml")
    parser.add_argument("--params-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/gazebo-acceptance")
    parser.add_argument("--adapter", type=Path, default=ROOT / "scripts/run_gazebo_attempt.sh")
    parser.add_argument("--total-timeout-sec", type=float, default=1800)
    parser.add_argument("--require-duration-regression", action="store_true")
    args = parser.parse_args()
    if not math.isfinite(args.total_timeout_sec) or args.total_timeout_sec <= 0:
        parser.error("--total-timeout-sec must be finite and positive")
    try:
        return run_experiment(
            config=args.config.resolve(), params=args.params_file.resolve(),
            output=args.output.resolve(), adapter=args.adapter.resolve(),
            total_timeout=args.total_timeout_sec,
            require_duration_regression=args.require_duration_regression,
        )
    except (ValueError, OSError) as exc:
        print(f"Gazebo acceptance input error: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
