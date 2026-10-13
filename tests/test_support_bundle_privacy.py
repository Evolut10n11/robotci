import json
from pathlib import Path

import pytest

from robotci.doctor import REQUIRED_ROS_PACKAGES, CheckResult, run_doctor_checks
from robotci.doctor_report import build_report
from robotci.support_bundle import _redact_doctor_checks, build_support_bundle, main

PRIVATE_MARKER = "PRIVATE_DIAGNOSTIC_8c093f"


@pytest.mark.parametrize(
    "name",
    ["platform", "ros2", "ROS_DISTRO", "docker", "runtime", *REQUIRED_ROS_PACKAGES],
)
@pytest.mark.parametrize("ok", [False, True])
def test_shared_checks_never_copy_diagnostic_text(name: str, ok: bool) -> None:
    original = CheckResult(
        name,
        ok,
        f"diagnostic at /private/{PRIVATE_MARKER} with token={PRIVATE_MARKER}",
        blocking=False,
        value=PRIVATE_MARKER,
    )

    redacted = _redact_doctor_checks([original])
    report = build_report(redacted)

    assert PRIVATE_MARKER not in json.dumps(report)
    assert redacted[0].name == name
    assert redacted[0].ok is ok
    assert redacted[0].blocking is False
    assert redacted[0].value is None
    assert report["status"] == "PASS"  # Nonblocking failures stay nonblocking.
    assert PRIVATE_MARKER in original.message  # Local diagnostics stay intact.
    assert original.value == PRIVATE_MARKER


@pytest.mark.parametrize("ok", [False, True])
@pytest.mark.parametrize("blocking", [False, True])
def test_unknown_check_is_anonymized_without_changing_verdict(ok: bool, blocking: bool) -> None:
    original = CheckResult(PRIVATE_MARKER, ok, PRIVATE_MARKER, blocking, PRIVATE_MARKER)

    redacted = _redact_doctor_checks([original])
    report = build_report(redacted)

    assert PRIVATE_MARKER not in json.dumps(report)
    assert redacted[0].name == "unknown"
    assert redacted[0].ok is ok
    assert redacted[0].blocking is blocking
    assert report["status"] == build_report([original])["status"]


@pytest.mark.parametrize("selected", ["native", "docker", "none", None, PRIVATE_MARKER])
def test_runtime_projection_preserves_only_known_values(selected: str | None, monkeypatch) -> None:
    monkeypatch.setenv("ROBOTCI_ATTEMPT_SCRIPT", f"/private/{PRIVATE_MARKER}/adapter.sh")
    original = CheckResult("runtime", selected != "none", PRIVATE_MARKER, value=selected)

    report = build_report(_redact_doctor_checks([original]))
    runtime = report["runtime"]

    assert runtime["selected"] == (selected if selected != PRIVATE_MARKER else None)
    assert runtime["adapter_override"] is (selected == "native")
    assert PRIVATE_MARKER not in json.dumps(report)
    assert PRIVATE_MARKER in json.dumps(build_report([original]))


def _write_config(path: Path) -> None:
    path.write_text(
        "version: 1\nruntime: auto\nscenarios:\n"
        "  - name: private_route\n"
        "    start: {x: 0, y: 0}\n"
        "    goal: {x: 1, y: 1}\n"
        "    timeout_sec: 30\n",
        encoding="utf-8",
    )


def test_real_doctor_env_and_os_errors_are_only_visible_locally(
    tmp_path: Path, monkeypatch
) -> None:
    config = tmp_path / "robotci.yaml"
    _write_config(config)
    monkeypatch.setenv("ROS_DISTRO", PRIVATE_MARKER)
    monkeypatch.setattr("robotci.doctor.command_exists", lambda command: command == "docker")
    monkeypatch.setattr("robotci.doctor._selected_runtime", lambda **_: "none")

    def failing_subprocess(*args, **kwargs):
        raise PermissionError(13, "Permission denied", f"/private/{PRIVATE_MARKER}/docker")

    monkeypatch.setattr("robotci.doctor.subprocess.run", failing_subprocess)
    checks = run_doctor_checks(require_ros=False)
    local = build_report(checks)
    messages = {check["name"]: check["message"] for check in local["checks"]}
    assert PRIVATE_MARKER in messages["ROS_DISTRO"]
    assert PRIVATE_MARKER in messages["docker"]
    monkeypatch.setattr("robotci.support_bundle.run_doctor_checks", lambda **_: checks)

    bundle = build_support_bundle(config_path=config, require_ros=False)

    assert PRIVATE_MARKER not in json.dumps(bundle)
    assert "private_route" not in json.dumps(bundle)
    assert bundle["doctor"]["status"] == local["status"]
    assert bundle["doctor"]["runtime"]["selected"] == "none"
    assert bundle["config"]["status"] == "PASS"


@pytest.mark.parametrize("compact", [False, True])
@pytest.mark.parametrize("ok", [False, True])
def test_stdout_serialization_keeps_privacy_and_exit_code(
    tmp_path: Path, monkeypatch, capsys, compact: bool, ok: bool
) -> None:
    config = tmp_path / "robotci.yaml"
    _write_config(config)
    checks = [
        CheckResult("ROS_DISTRO", False, f"ROS_DISTRO={PRIVATE_MARKER}", blocking=False),
        CheckResult("docker", ok, f"docker info failed: /private/{PRIVATE_MARKER}", blocking=False),
        CheckResult("runtime", ok, PRIVATE_MARKER, value="docker" if ok else "none"),
    ]
    monkeypatch.setattr("robotci.support_bundle.run_doctor_checks", lambda **_: checks)
    argv = ["--config", str(config), "--output", "-"]
    if compact:
        argv.append("--compact")

    exit_code = main(argv)
    captured = capsys.readouterr()
    bundle = json.loads(captured.out)

    assert exit_code == (0 if ok else 1)
    assert bundle["status"] == ("PASS" if ok else "FAIL")
    assert PRIVATE_MARKER not in captured.out
    assert captured.err == ""
    if compact:
        assert captured.out.count("\n") == 1
