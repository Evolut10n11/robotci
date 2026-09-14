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
    RuntimeVariable,
    _resolve_attempt_script,
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


def _environment(
    *,
    python_version: str = "3.12.3",
    containerized: bool = False,
    runtime_variables: tuple[RuntimeVariable, ...] = (),
):
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
        runtime_variables=runtime_variables,
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


def test_environment_fingerprint_covers_runtime_variables() -> None:
    original = _environment(
        runtime_variables=(
            RuntimeVariable(name="ROS_DOMAIN_ID", value="7"),
            RuntimeVariable(name="RMW_IMPLEMENTATION", value="rmw_fastrtps_cpp"),
        )
    )
    changed = _environment(
        runtime_variables=(
            RuntimeVariable(name="ROS_DOMAIN_ID", value="8"),
            RuntimeVariable(name="RMW_IMPLEMENTATION", value="rmw_fastrtps_cpp"),
        )
    )

    assert original.fingerprint != changed.fingerprint
    assert original.runtime_variables[0].name == "RMW_IMPLEMENTATION"
    assert original.runtime_variables[1].name == "ROS_DOMAIN_ID"


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


def test_capture_suite_execution_can_build_docker_image(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    environment = _environment(containerized=True)

    def fake_run(command, **kwargs):
        assert command == [
            "docker",
            "compose",
            "run",
            "--rm",
            "--no-deps",
            "--build",
            "robotci",
            "python",
            "-m",
            "robotci.reproducibility",
        ]
        assert kwargs["timeout"] == 300
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
        build_docker_image=True,
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


def test_robotci_source_fingerprint_prefers_runtime_package(
    tmp_path: Path,
) -> None:
    installed_package = tmp_path / "site-packages" / "robotci"
    runtime = tmp_path / "runtime"
    runtime_package = runtime / "robotci"
    installed_package.mkdir(parents=True)
    runtime_package.mkdir(parents=True)
    (runtime / "scripts").mkdir()
    installed_source = installed_package / "runner.py"
    runtime_source = runtime_package / "runner.py"
    installed_source.write_text("INSTALLED = 1\n", encoding="utf-8")
    runtime_source.write_text("RUNTIME = 1\n", encoding="utf-8")

    original = build_robotci_source_fingerprint(
        installed_package,
        runtime_root=runtime,
    )
    installed_source.write_text("INSTALLED = 2\n", encoding="utf-8")
    installed_changed = build_robotci_source_fingerprint(
        installed_package,
        runtime_root=runtime,
    )
    runtime_source.write_text("RUNTIME = 2\n", encoding="utf-8")
    runtime_changed = build_robotci_source_fingerprint(
        installed_package,
        runtime_root=runtime,
    )

    assert original == installed_changed
    assert original != runtime_changed


def test_robotci_source_fingerprint_covers_external_attempt_script(
    tmp_path: Path,
) -> None:
    package = tmp_path / "robotci"
    runtime = tmp_path / "runtime"
    package.mkdir()
    (runtime / "scripts").mkdir(parents=True)
    (package / "runner.py").write_text("VALUE = 1\n", encoding="utf-8")
    (runtime / "scripts" / "run.sh").write_text("exit 0\n", encoding="utf-8")
    attempt = tmp_path / "adapter.sh"
    attempt.write_text("exit 0\n", encoding="utf-8")

    original = build_robotci_source_fingerprint(
        package,
        runtime_root=runtime,
        attempt_script=attempt,
    )
    attempt.write_text("exit 1\n", encoding="utf-8")

    assert original != build_robotci_source_fingerprint(
        package,
        runtime_root=runtime,
        attempt_script=attempt,
    )


def test_robotci_source_fingerprint_covers_selected_internal_attempt_script(
    tmp_path: Path,
) -> None:
    package = tmp_path / "robotci"
    runtime = tmp_path / "runtime"
    scripts = runtime / "scripts"
    package.mkdir()
    scripts.mkdir(parents=True)
    (package / "runner.py").write_text("VALUE = 1\n", encoding="utf-8")
    first = scripts / "first.sh"
    second = scripts / "second.sh"
    first.write_text("exit 0\n", encoding="utf-8")
    second.write_text("exit 0\n", encoding="utf-8")

    first_selected = build_robotci_source_fingerprint(
        package,
        runtime_root=runtime,
        attempt_script=first,
    )
    second_selected = build_robotci_source_fingerprint(
        package,
        runtime_root=runtime,
        attempt_script=second,
    )

    assert first_selected != second_selected


def test_attempt_script_resolution_preserves_literal_tilde(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ROBOTCI_ATTEMPT_SCRIPT", "~/adapter.sh")

    attempt_script, identity = _resolve_attempt_script(tmp_path)

    assert attempt_script == tmp_path / "~" / "adapter.sh"
    assert identity == "environment:~/adapter.sh"


def test_robotci_source_fingerprint_preserves_selected_symlink(
    tmp_path: Path,
) -> None:
    package = tmp_path / "robotci"
    runtime = tmp_path / "runtime"
    scripts = runtime / "scripts"
    package.mkdir()
    scripts.mkdir(parents=True)
    (package / "runner.py").write_text("VALUE = 1\n", encoding="utf-8")
    target = scripts / "target.sh"
    alias = scripts / "alias.sh"
    target.write_text("exit 0\n", encoding="utf-8")
    try:
        alias.symlink_to(target.name)
    except OSError:
        pytest.skip("symlinks are unavailable on this platform")

    target_selected = build_robotci_source_fingerprint(
        package,
        runtime_root=runtime,
        attempt_script=target,
    )
    alias_selected = build_robotci_source_fingerprint(
        package,
        runtime_root=runtime,
        attempt_script=alias,
    )

    assert target_selected != alias_selected


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
