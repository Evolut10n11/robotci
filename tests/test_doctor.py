import sys

from robotci.doctor import command_exists, run_doctor_checks


def test_current_python_executable_exists() -> None:
    assert command_exists(sys.executable)


def test_missing_command_returns_false() -> None:
    assert not command_exists("robotci-command-that-does-not-exist")


def test_ros_checks_are_non_blocking_when_ros_is_optional(monkeypatch) -> None:
    monkeypatch.setattr("robotci.doctor.command_exists", lambda _command: False)

    checks = run_doctor_checks(require_ros=False)
    ros_checks = [check for check in checks if check.name != "platform"]

    assert ros_checks
    assert all(not check.blocking for check in ros_checks)


def test_ros_checks_are_blocking_when_ros_is_required(monkeypatch) -> None:
    monkeypatch.setattr("robotci.doctor.command_exists", lambda _command: False)

    checks = run_doctor_checks(require_ros=True)
    ros_checks = [check for check in checks if check.name != "platform"]

    assert ros_checks
    assert all(check.blocking for check in ros_checks)
