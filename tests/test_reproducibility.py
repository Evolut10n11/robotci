from __future__ import annotations

import json
import os
import subprocess
from dataclasses import asdict, replace
from importlib.machinery import EXTENSION_SUFFIXES
from pathlib import Path

import pytest

from robotci.config import PoseConfig, RobotCIConfig, ScenarioConfig
from robotci.reproducibility import (
    RUNTIME_CONTRACT,
    ReproducibilityError,
    RuntimePackage,
    RuntimeVariable,
    _installed_debian_packages,
    _resolve_attempt_script,
    _runtime_variables,
    build_robotci_source_fingerprint,
    build_runtime_environment,
    build_suite_execution_identity,
    build_suite_plan_fingerprint,
    capture_suite_execution,
    collect_runtime_environment,
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
            RuntimeVariable(name="ROS_DOMAIN_ID", value="sha256:" + "7" * 64),
            RuntimeVariable(name="RMW_IMPLEMENTATION", value="sha256:" + "4" * 64),
        )
    )
    changed = _environment(
        runtime_variables=(
            RuntimeVariable(name="ROS_DOMAIN_ID", value="sha256:" + "8" * 64),
            RuntimeVariable(name="RMW_IMPLEMENTATION", value="sha256:" + "4" * 64),
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


def test_execution_parser_rejects_noncanonical_container_runtime() -> None:
    execution = build_suite_execution_identity(
        runtime="native",
        plan_fingerprint=build_suite_plan_fingerprint(_config(), timeout_sec=None),
        environment=_environment(containerized=True),
    )
    payload = asdict(execution)
    payload["runtime"] = "native"

    with pytest.raises(
        ReproducibilityError,
        match="runtime is inconsistent with its environment",
    ):
        parse_suite_execution(payload)


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


@pytest.mark.parametrize("variable", ["LD_AUDIT", "LD_PRELOAD"])
def test_runtime_environment_rejects_loader_injection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    variable: str,
) -> None:
    monkeypatch.setenv(variable, str(tmp_path / "injected.so"))

    with pytest.raises(
        ReproducibilityError,
        match="loader injection is unsupported",
    ):
        collect_runtime_environment(tmp_path)


def test_runtime_variables_hide_values_and_hash_file_backed_configuration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configuration = tmp_path / "cyclonedds.xml"
    configuration.write_text("<CycloneDDS/>\n", encoding="utf-8")
    keystore = tmp_path / "keystore"
    enclave = keystore / "enclaves" / "robotci"
    enclave.mkdir(parents=True)
    certificate = enclave / "cert.pem"
    certificate.write_text("certificate-v1\n", encoding="utf-8")
    monkeypatch.setenv("CYCLONEDDS_URI", str(configuration))
    monkeypatch.setenv("ROS_SECURITY_KEYSTORE", str(keystore))
    monkeypatch.setenv("ROS_API_TOKEN", "super-secret")
    monkeypatch.setenv("RCUTILS_CONSOLE_OUTPUT_FORMAT", "{message}")

    first = {item.name: item.value for item in _runtime_variables(tmp_path)}
    serialized = json.dumps(first)

    assert "super-secret" not in serialized
    assert str(configuration) not in serialized
    assert str(keystore) not in serialized
    assert first["ROS_API_TOKEN"].startswith("sha256:")
    assert len(first["ROS_API_TOKEN"]) == 71
    assert first["RCUTILS_CONSOLE_OUTPUT_FORMAT"].startswith("sha256:")
    assert "{message}" not in serialized

    configuration.write_text("<CycloneDDS><Domain/></CycloneDDS>\n", encoding="utf-8")
    certificate.write_text("certificate-v2\n", encoding="utf-8")
    changed = {item.name: item.value for item in _runtime_variables(tmp_path)}

    assert first["ROS_API_TOKEN"] == changed["ROS_API_TOKEN"]
    assert first["CYCLONEDDS_URI"] != changed["CYCLONEDDS_URI"]
    assert first["ROS_SECURITY_KEYSTORE"] != changed["ROS_SECURITY_KEYSTORE"]

    real_scandir = os.scandir

    def deny_enclave(path):
        if Path(path) == enclave:
            raise PermissionError("keystore directory cannot be enumerated")
        return real_scandir(path)

    monkeypatch.setattr("robotci.reproducibility.os.scandir", deny_enclave)
    with pytest.raises(
        ReproducibilityError,
        match="cannot walk directory-backed runtime variable ROS_SECURITY_KEYSTORE",
    ):
        _runtime_variables(tmp_path)


def test_runtime_variables_reject_remote_configuration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CYCLONEDDS_URI", "https://example.invalid/cyclonedds.xml")

    with pytest.raises(
        ReproducibilityError,
        match="remote runtime configuration is unsupported",
    ):
        _runtime_variables(tmp_path)


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


def test_debian_package_inventory_covers_installed_dependency_closure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("RMW_IMPLEMENTATION", raising=False)
    monkeypatch.setattr(
        "robotci.reproducibility._DEBIAN_PACKAGES",
        ("ros-jazzy-navigation2",),
    )
    output = (
        "hi \tros-jazzy-navigation2\t1.0\tros-jazzy-rclpy, "
        "rmw-implementation\t\t\n"
        "ii \tros-jazzy-rclpy\t2.0\tpython3:any\t\t\n"
        "ii \trmw-fastrtps-cpp\t3.0\tlibfastdds\t\t"
        "rmw-implementation\n"
        "ii \tlibfastdds:amd64\t4.0\t\tlibc6\t\n"
        "ii \tpython3\t3.12\tlibc6\t\t\n"
        "ii \tlibc6:amd64\t2.39\t\t\t\n"
        "ii \tunrelated\t9.9\t\t\t\n"
    )

    def fake_run(command, **kwargs):
        assert command[0:2] == ["dpkg-query", "-W"]
        return subprocess.CompletedProcess(command, 0, stdout=output, stderr="")

    monkeypatch.setattr("robotci.reproducibility.subprocess.run", fake_run)

    packages = _installed_debian_packages()

    assert [(package.name, package.version) for package in packages] == [
        ("libc6:amd64", "2.39"),
        ("libfastdds:amd64", "4.0"),
        ("python3", "3.12"),
        ("rmw-fastrtps-cpp", "3.0"),
        ("ros-jazzy-navigation2", "1.0"),
        ("ros-jazzy-rclpy", "2.0"),
    ]


def test_debian_package_inventory_includes_selected_rmw(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "robotci.reproducibility._DEBIAN_PACKAGES",
        ("bash",),
    )
    monkeypatch.setenv("RMW_IMPLEMENTATION", "rmw_cyclonedds_cpp")
    output = (
        "ii \tbash\t5.2\t\t\t\n"
        "ii \tros-jazzy-rmw-cyclonedds-cpp\t2.2\t\t\t\n"
    )

    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(command, 0, stdout=output, stderr="")

    monkeypatch.setattr("robotci.reproducibility.subprocess.run", fake_run)

    packages = _installed_debian_packages()

    assert [(package.name, package.version) for package in packages] == [
        ("bash", "5.2"),
        ("ros-jazzy-rmw-cyclonedds-cpp", "2.2"),
    ]


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


def test_robotci_source_fingerprint_covers_runner_and_runtime_packages(
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
    shadow_source = runtime / "rclpy.py"
    shadow_bytecode = runtime / "rclpy.pyc"
    shadow_extension = runtime / f"rclpy{EXTENSION_SUFFIXES[0]}"
    shadow_package = runtime / "nav2_simple_commander"
    shadow_package.mkdir()
    shadow_init = shadow_package / "__init__.pyc"
    shadow_data = shadow_package / "profile.xml"
    installed_source.write_text("INSTALLED = 1\n", encoding="utf-8")
    runtime_source.write_text("RUNTIME = 1\n", encoding="utf-8")
    shadow_source.write_text("SHADOW = 1\n", encoding="utf-8")
    shadow_bytecode.write_bytes(b"BYTECODE-1")
    shadow_extension.write_bytes(b"EXTENSION-1")
    shadow_init.write_bytes(b"PACKAGE-1")
    shadow_data.write_text("<profile>1</profile>\n", encoding="utf-8")

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
    shadow_source.write_text("SHADOW = 2\n", encoding="utf-8")
    shadow_changed = build_robotci_source_fingerprint(
        installed_package,
        runtime_root=runtime,
    )
    shadow_bytecode.write_bytes(b"BYTECODE-2")
    bytecode_changed = build_robotci_source_fingerprint(
        installed_package,
        runtime_root=runtime,
    )
    shadow_extension.write_bytes(b"EXTENSION-2")
    extension_changed = build_robotci_source_fingerprint(
        installed_package,
        runtime_root=runtime,
    )
    shadow_data.write_text("<profile>2</profile>\n", encoding="utf-8")
    package_data_changed = build_robotci_source_fingerprint(
        installed_package,
        runtime_root=runtime,
    )

    assert original != installed_changed
    assert installed_changed != runtime_changed
    assert runtime_changed != shadow_changed
    assert shadow_changed != bytecode_changed
    assert bytecode_changed != extension_changed
    assert extension_changed != package_data_changed


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
