import sys

from robotci.doctor import command_exists, run_doctor_checks
from robotci.platform import PlatformInfo
from robotci.runner import RuntimeUnavailableError


def _checks_by_name(checks):
    return {check.name: check for check in checks}


def _runtime_unavailable(_requested):
    raise RuntimeUnavailableError("unavailable")


def test_current_python_executable_exists() -> None:
    assert command_exists(sys.executable)


def test_missing_command_returns_false() -> None:
    assert not command_exists("robotci-command-that-does-not-exist")


def test_runtime_diagnostics_are_non_blocking_when_runtime_is_optional(monkeypatch) -> None:
    monkeypatch.setattr("robotci.doctor.command_exists", lambda _command: False)
    monkeypatch.setattr(
        "robotci.doctor.get_docker_status",
        lambda: (False, "docker command was not found"),
    )
    monkeypatch.setattr("robotci.doctor.select_runtime", _runtime_unavailable)

    checks = run_doctor_checks(require_ros=False)
    runtime_checks = [check for check in checks if check.name != "platform"]

    assert runtime_checks
    assert all(not check.blocking for check in runtime_checks)


def test_default_runtime_uses_docker_fallback(monkeypatch) -> None:
    monkeypatch.setattr(
        "robotci.doctor.current_platform",
        lambda: PlatformInfo("Windows", core_supported=True, ros_runtime_supported=False),
    )
    monkeypatch.setattr("robotci.doctor.command_exists", lambda _command: False)
    monkeypatch.setattr(
        "robotci.doctor.get_docker_status",
        lambda: (True, "docker daemon is available"),
    )
    monkeypatch.setattr("robotci.doctor.select_runtime", lambda _requested: "docker")
    monkeypatch.delenv("ROS_DISTRO", raising=False)

    checks = _checks_by_name(run_doctor_checks())

    assert checks["docker"].ok
    assert checks["runtime"].ok
    assert checks["runtime"].blocking
    assert checks["runtime"].value == "docker"
    assert checks["runtime"].message == "auto runtime will use Docker"
    assert not checks["ros2"].blocking


def test_default_runtime_uses_native_ros_when_ready(monkeypatch) -> None:
    monkeypatch.setattr(
        "robotci.doctor.current_platform",
        lambda: PlatformInfo("Linux", core_supported=True, ros_runtime_supported=True),
    )
    monkeypatch.setattr("robotci.doctor.command_exists", lambda command: command == "ros2")
    monkeypatch.setattr(
        "robotci.doctor.get_ros_package_prefix",
        lambda package: f"/opt/ros/jazzy/share/{package}",
    )
    monkeypatch.setattr(
        "robotci.doctor.get_docker_status",
        lambda: (False, "docker command was not found"),
    )
    monkeypatch.setattr("robotci.doctor.select_runtime", lambda _requested: "native")
    monkeypatch.setenv("ROS_DISTRO", "jazzy")

    checks = _checks_by_name(run_doctor_checks())

    assert checks["runtime"].ok
    assert checks["runtime"].value == "native"
    assert checks["runtime"].message == "auto runtime will use native ROS2 Jazzy/Nav2"
    assert not checks["docker"].ok


def test_default_runtime_fails_when_no_runtime_is_available(monkeypatch) -> None:
    monkeypatch.setattr(
        "robotci.doctor.current_platform",
        lambda: PlatformInfo("Windows", core_supported=True, ros_runtime_supported=False),
    )
    monkeypatch.setattr("robotci.doctor.command_exists", lambda _command: False)
    monkeypatch.setattr(
        "robotci.doctor.get_docker_status",
        lambda: (False, "docker command was not found"),
    )
    monkeypatch.setattr("robotci.doctor.select_runtime", _runtime_unavailable)
    monkeypatch.delenv("ROS_DISTRO", raising=False)

    checks = _checks_by_name(run_doctor_checks())

    assert not checks["runtime"].ok
    assert checks["runtime"].blocking
    assert checks["runtime"].value == "none"
    assert "no usable runtime found" in checks["runtime"].message


def test_selected_runtime_matches_runner_when_ros_is_installed_but_unsourced(monkeypatch) -> None:
    monkeypatch.setattr(
        "robotci.doctor.current_platform",
        lambda: PlatformInfo("Linux", core_supported=True, ros_runtime_supported=True),
    )
    monkeypatch.setattr("robotci.doctor.command_exists", lambda _command: False)
    monkeypatch.setattr(
        "robotci.doctor.get_docker_status",
        lambda: (True, "docker daemon is available"),
    )
    monkeypatch.setattr("robotci.doctor.select_runtime", lambda _requested: "native")
    monkeypatch.delenv("ROS_DISTRO", raising=False)

    checks = _checks_by_name(run_doctor_checks())

    assert not checks["ros2"].ok
    assert checks["docker"].ok
    assert checks["runtime"].ok
    assert checks["runtime"].value == "native"
    assert checks["runtime"].message == "auto runtime will use native ROS2 Jazzy/Nav2"


def test_strict_ros_mode_is_not_satisfied_by_docker(monkeypatch) -> None:
    monkeypatch.setattr(
        "robotci.doctor.current_platform",
        lambda: PlatformInfo("Linux", core_supported=True, ros_runtime_supported=True),
    )
    monkeypatch.setattr("robotci.doctor.command_exists", lambda _command: False)
    monkeypatch.setattr(
        "robotci.doctor.get_docker_status",
        lambda: (True, "docker daemon is available"),
    )
    monkeypatch.setattr("robotci.doctor.select_runtime", _runtime_unavailable)
    monkeypatch.delenv("ROS_DISTRO", raising=False)

    checks = _checks_by_name(run_doctor_checks(require_ros=True))

    strict_names = {
        "ros2",
        "ROS_DISTRO",
        "nav2_bringup",
        "nav2_loopback_sim",
        "nav2_simple_commander",
        "runtime",
    }
    assert all(checks[name].blocking for name in strict_names)
    assert not checks["runtime"].ok
    assert checks["runtime"].value == "none"
    assert checks["runtime"].message == "native ROS2 Jazzy/Nav2 runtime is incomplete"
    assert checks["docker"].ok
    assert not checks["docker"].blocking
