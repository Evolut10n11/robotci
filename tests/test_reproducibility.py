from __future__ import annotations

import json
import subprocess
from dataclasses import asdict, replace
from pathlib import Path

import pytest

from robotci.config import PoseConfig, RobotCIConfig, ScenarioConfig
from robotci.reproducibility import (
    RUNTIME_CONTRACT,
    ReproducibilityError,
    RuntimePackage,
    build_robotci_source_fingerprint,
    build_runtime_environment,
    build_suite_execution_identity,
    build_suite_plan_fingerprint,
    capture_suite_execution,
    parse_runtime_environment,
    parse_suite_execution,
    validate_suite_execution,
)


def _config(*, timeout_sec: float = 10.0, tolerance: float = 0.25) -> RobotCIConfig:
    return RobotCIConfig(
        version=1,
        runtime="native",
        scenarios=(
            ScenarioConfig(
                name="route",
                start=PoseConfig(x=-0.0, y=0.0),
                goal=PoseConfig(x=1.0, y=2.0),
                timeout_sec=timeout_sec,
                map_id="warehouse-v1",
                goal_tolerance_m=tolerance,
                min_feedback_samples=2,
            ),
        ),
    )


def _environment(*, python_version: str = "3.12.3", containerized: bool = False):
    return build_runtime_environment(
        os_id="ubuntu",
        os_version="24.04",
        architecture="x86_64",
        python_version=python_version,
        ros_distro="jazzy",
        robotci_build="sha256:" + "2" * 64,
        containerized=containerized,
        packages=(
            RuntimePackage(manager="python", name="robotci", version="0.0.1"),
            RuntimePackage(manager="deb", name="ros-jazzy-navigation2", version="1.3.8"),
        ),
    )


def test_plan_fingerprint_is_stable_and_covers_effective_inputs() -> None:
    original = build_suite_plan_fingerprint(_config(), timeout_sec=None)
    equivalent = build_suite_plan_fingerprint(
        replace(
            _config(),
            scenarios=(
                replace(
                    _config().scenarios[0],
                    start=PoseConfig(x=0.0, y=-0.0, yaw=0.0),
                ),
            ),
        ),
        timeout_sec=None,
    )
    changed_timeout = build_suite_plan_fingerprint(_config(timeout_sec=11.0), timeout_sec=None)
    overridden = build_suite_plan_fingerprint(_config(timeout_sec=11.0), timeout_sec=10.0)
    changed_policy = build_suite_plan_fingerprint(
        _config(tolerance=0.3),
        timeout_sec=None,
    )

    assert original == equivalent == overridden
    assert original != changed_timeout
    assert original != changed_policy


def test_environment_fingerprint_is_independent_of_package_order() -> None:
    environment = _environment()
    reversed_environment = build_runtime_environment(
        os_id=environment.os_id,
        os_version=environment.os_version,
        architecture=environment.architecture,
        python_version=environment.python_version,
        ros_distro=environment.ros_distro,
        robotci_build=environment.robotci_build,
        containerized=environment.containerized,
        packages=tuple(reversed(environment.packages)),
    )

    assert environment == reversed_environment


def test_environment_parser_rejects_tampered_contents() -> None:
    payload = asdict(_environment())
    payload["python_version"] = "3.12.99"

    with pytest.raises(ReproducibilityError, match="fingerprint does not match"):
        parse_runtime_environment(payload)


def test_execution_parser_rejects_tampered_plan() -> None:
    execution = build_suite_execution_identity(
        runtime="native",
        plan_fingerprint=build_suite_plan_fingerprint(_config(), timeout_sec=None),
        environment=_environment(),
    )
    payload = asdict(execution)
    payload["plan_fingerprint"] = "sha256:" + "f" * 64

    with pytest.raises(ReproducibilityError, match="fingerprint does not match"):
        parse_suite_execution(payload)


def test_container_environment_normalizes_runtime_to_docker() -> None:
    execution = build_suite_execution_identity(
        runtime="native",
        plan_fingerprint=build_suite_plan_fingerprint(_config(), timeout_sec=None),
        environment=_environment(containerized=True),
    )

    assert execution.runtime == "docker"
    assert execution.runtime_contract == RUNTIME_CONTRACT


def test_capture_suite_execution_reads_environment_from_docker(
    tmp_path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    environment = _environment(containerized=True)

    def fake_run(command, **kwargs):
        assert command == [
            "docker",
            "compose",
            "run",
            "--rm",
            "--no-deps",
            "robotci",
            "python",
            "-m",
            "robotci.reproducibility",
        ]
        assert kwargs["cwd"] == tmp_path
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps(asdict(environment)),
            stderr="",
        )

    monkeypatch.setattr("robotci.reproducibility.subprocess.run", fake_run)

    execution = capture_suite_execution(
        config=_config(),
        timeout_sec=None,
        runtime="docker",
        runtime_root=tmp_path,
    )

    assert execution.runtime == "docker"
    assert execution.environment == environment


def test_duplicate_runtime_packages_are_rejected() -> None:
    package = RuntimePackage(manager="python", name="robotci", version="0.0.1")

    with pytest.raises(ReproducibilityError, match="duplicate runtime package"):
        build_runtime_environment(
            os_id="ubuntu",
            os_version="24.04",
            architecture="x86_64",
            python_version="3.12.3",
            ros_distro="jazzy",
            robotci_build="sha256:" + "2" * 64,
            containerized=False,
            packages=(package, package),
        )


def test_robotci_source_fingerprint_uses_separate_runtime_root(tmp_path: Path) -> None:
    package = tmp_path / "site-packages" / "robotci"
    runtime = tmp_path / "workspace"
    scripts = runtime / "scripts"
    package.mkdir(parents=True)
    scripts.mkdir(parents=True)
    (package / "runner.py").write_text("VALUE = 1\n", encoding="utf-8")
    script = scripts / "run.sh"
    script.write_text("exit 0\n", encoding="utf-8")

    original = build_robotci_source_fingerprint(package, runtime_root=runtime)
    script.write_text("exit 1\n", encoding="utf-8")

    assert original != build_robotci_source_fingerprint(
        package,
        runtime_root=runtime,
    )


def test_boolean_provenance_schema_versions_are_rejected() -> None:
    environment_payload = asdict(_environment())
    environment_payload["schema_version"] = True
    with pytest.raises(ReproducibilityError, match="schema_version must be 1"):
        parse_runtime_environment(environment_payload)

    execution = build_suite_execution_identity(
        runtime="native",
        plan_fingerprint=build_suite_plan_fingerprint(_config(), timeout_sec=None),
        environment=_environment(),
    )
    execution_payload = asdict(execution)
    execution_payload["schema_version"] = True
    with pytest.raises(ReproducibilityError, match="schema_version must be 1"):
        parse_suite_execution(execution_payload)

    suite_payload = {
        "schema_version": True,
        "runtime": execution.runtime,
        "execution": asdict(execution),
    }
    with pytest.raises(ReproducibilityError, match="schema_version must be 1"):
        validate_suite_execution(suite_payload)
