from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from pathlib import Path

import pytest

from robotci import doctor, native_runtime, runner
from robotci.platform import PlatformInfo


@pytest.mark.parametrize("returncode,ready", [(0, True), (1, False), (3, False), (127, False)])
def test_native_probe_uses_bounded_shell_command(monkeypatch, returncode, ready) -> None:
    def fake_run(command, **kwargs):
        assert command[:2] == ["bash", "-c"]
        assert command[-3:] == list(native_runtime.REQUIRED_ROS_PACKAGES)
        assert kwargs["timeout"] == 25
        assert kwargs["check"] is False
        assert kwargs.get("shell", False) is False
        return subprocess.CompletedProcess(command, returncode)

    monkeypatch.setattr(native_runtime.subprocess, "run", fake_run)
    assert native_runtime.probe_native_ros() is ready


@pytest.mark.parametrize("error", [OSError("bash missing"), subprocess.TimeoutExpired("bash", 25)])
def test_native_probe_errors_fail_closed(monkeypatch, error) -> None:
    def failed_run(*args, **kwargs):
        raise error

    monkeypatch.setattr(native_runtime.subprocess, "run", failed_run)
    assert native_runtime.probe_native_ros() is False


def test_native_runtime_rejects_windows_before_invoking_bash(monkeypatch) -> None:
    monkeypatch.setattr(runner.stdlib_platform, "system", lambda: "Windows")
    monkeypatch.setattr(runner, "probe_native_ros", lambda: pytest.fail("no bash on Windows"))
    assert runner._native_ros_available() is False


@pytest.fixture
def fake_ros(tmp_path: Path, monkeypatch):
    if os.name == "nt" or not shutil.which("bash") or not shutil.which("timeout"):
        pytest.skip("POSIX shell and timeout required")
    bin_dir = tmp_path / "fake ros/bin"
    bin_dir.mkdir(parents=True)
    ros2 = bin_dir / "ros2"
    ros2.write_text(
        '''#!/bin/sh
[ "$1" = "pkg" ] && [ "$2" = "prefix" ] || exit 2
[ "$3" != "${MISSING_PACKAGE:-}" ] || exit 1
printf '/fake/jazzy/%s\\n' "$3"
''', encoding="utf-8",
    )
    ros2.chmod(0o755)
    setup = tmp_path / "unsourced jazzy/setup.bash"
    setup.parent.mkdir()
    monkeypatch.setattr(native_runtime, "ROS_SETUP", setup)
    monkeypatch.setattr(runner.stdlib_platform, "system", lambda: "Linux")
    monkeypatch.setattr(runner, "_docker_available", lambda: False)
    monkeypatch.delenv("MISSING_PACKAGE", raising=False)
    monkeypatch.delenv("ROS_DISTRO", raising=False)
    # Current-shell diagnostics deliberately remain separate from the effective
    # subprocess environment used by the runner/default doctor readiness verdict.
    monkeypatch.setattr(doctor, "current_platform", lambda: PlatformInfo("Linux", True, True))
    monkeypatch.setattr(doctor, "command_exists", lambda command: command == "ros2")
    monkeypatch.setattr(doctor, "get_ros_package_prefix", lambda package: None)
    monkeypatch.setattr(doctor, "get_docker_status", lambda: (False, "not installed"))
    return bin_dir, setup


@pytest.mark.parametrize("distro", ["humble", "rolling", ""])
def test_wrong_distro_is_rejected_by_runner_and_default_doctor(fake_ros, monkeypatch, distro):
    bin_dir, _ = fake_ros
    monkeypatch.setenv("PATH", str(bin_dir) + os.pathsep + os.environ["PATH"])
    monkeypatch.setenv("ROS_DISTRO", distro)
    with pytest.raises(runner.RuntimeUnavailableError):
        runner.select_runtime("native")
    checks = {check.name: check for check in doctor.run_doctor_checks()}
    assert not checks["runtime"].ok
    assert checks["runtime"].value == "none"
    assert any(not check.ok and check.blocking for check in checks.values())


@pytest.mark.parametrize("package", native_runtime.REQUIRED_ROS_PACKAGES)
def test_each_missing_nav2_package_rejects_native_and_allows_docker_fallback(
    fake_ros, monkeypatch, package,
):
    bin_dir, _ = fake_ros
    monkeypatch.setenv("PATH", str(bin_dir) + os.pathsep + os.environ["PATH"])
    monkeypatch.setenv("ROS_DISTRO", "jazzy")
    monkeypatch.setenv("MISSING_PACKAGE", package)
    with pytest.raises(runner.RuntimeUnavailableError):
        runner.select_runtime("native")
    monkeypatch.setattr(runner, "_docker_available", lambda: True)
    monkeypatch.setattr(doctor, "get_docker_status", lambda: (True, "ready"))
    assert runner.select_runtime() == "docker"
    checks = {check.name: check for check in doctor.run_doctor_checks()}
    assert checks["runtime"].ok
    assert checks["runtime"].value == "docker"


def test_unsourced_jazzy_is_verified_after_sourcing_setup(fake_ros, monkeypatch):
    bin_dir, setup = fake_ros
    setup.write_text(
        f"export PATH={shlex.quote(str(bin_dir))}:\"$PATH\"\nexport ROS_DISTRO=jazzy\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(doctor, "command_exists", lambda command: False)
    assert runner.select_runtime("auto") == "native"
    checks = {check.name: check for check in doctor.run_doctor_checks()}
    assert not checks["ros2"].ok  # Shell inventory is not a readiness claim.
    assert checks["runtime"].ok
    assert checks["runtime"].value == "native"
    assert "ROS_DISTRO" not in os.environ  # The parent process was not modified.


def test_setup_file_without_working_packages_is_not_enough(fake_ros, monkeypatch):
    bin_dir, setup = fake_ros
    setup.write_text(
        f"export PATH={shlex.quote(str(bin_dir))}:\"$PATH\"\nexport ROS_DISTRO=jazzy\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("MISSING_PACKAGE", "nav2_bringup")
    with pytest.raises(runner.RuntimeUnavailableError):
        runner.select_runtime()


def test_failed_setup_is_rejected_even_when_parent_shell_looks_ready(fake_ros, monkeypatch):
    bin_dir, setup = fake_ros
    monkeypatch.setenv("PATH", str(bin_dir) + os.pathsep + os.environ["PATH"])
    monkeypatch.setenv("ROS_DISTRO", "jazzy")
    setup.write_text("return 1\n", encoding="utf-8")
    assert runner._native_ros_available() is False


def test_strict_doctor_cannot_override_a_failed_runtime_probe(fake_ros, monkeypatch):
    bin_dir, setup = fake_ros
    monkeypatch.setenv("PATH", str(bin_dir) + os.pathsep + os.environ["PATH"])
    monkeypatch.setenv("ROS_DISTRO", "jazzy")
    monkeypatch.setattr(doctor, "get_ros_package_prefix", lambda package: f"/fake/{package}")
    setup.write_text("return 1\n", encoding="utf-8")
    checks = {check.name: check for check in doctor.run_doctor_checks(require_ros=True)}
    assert checks["ros2"].ok
    assert checks["ROS_DISTRO"].ok
    assert all(checks[package].ok for package in native_runtime.REQUIRED_ROS_PACKAGES)
    assert checks["runtime"].value == "none"
    assert not checks["runtime"].ok
