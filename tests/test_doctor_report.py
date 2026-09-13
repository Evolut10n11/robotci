import json

from robotci.doctor import CheckResult
from robotci.doctor_report import build_report, main


def test_build_report_passes_with_only_non_blocking_failures() -> None:
    report = build_report(
        [
            CheckResult("platform", True, "supported"),
            CheckResult("docker", False, "not available", blocking=False),
            CheckResult("runtime", True, "auto runtime will use native ROS2 Jazzy/Nav2"),
        ]
    )

    assert report["schema_version"] == 1
    assert report["status"] == "PASS"
    assert report["runtime"] == {
        "ok": True,
        "message": "auto runtime will use native ROS2 Jazzy/Nav2",
    }


def test_build_report_fails_on_blocking_failure() -> None:
    report = build_report(
        [
            CheckResult("platform", True, "supported"),
            CheckResult("runtime", False, "no usable runtime found"),
        ]
    )

    assert report["status"] == "FAIL"
    assert report["checks"][1]["blocking"] is True


def test_main_writes_json_and_returns_success(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        "robotci.doctor_report.run_doctor_checks",
        lambda require_ros=None: [
            CheckResult("platform", True, "supported"),
            CheckResult("runtime", True, "auto runtime will use Docker"),
        ],
    )
    output = tmp_path / "diagnostics" / "doctor.json"

    exit_code = main(["--output", str(output)])

    assert exit_code == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["status"] == "PASS"
    assert report["runtime"]["message"] == "auto runtime will use Docker"


def test_main_forwards_strict_native_mode(monkeypatch, tmp_path) -> None:
    received: list[bool | None] = []

    def fake_checks(require_ros=None):
        received.append(require_ros)
        return [CheckResult("runtime", False, "native runtime incomplete")]

    monkeypatch.setattr("robotci.doctor_report.run_doctor_checks", fake_checks)

    exit_code = main(["--require-ros", "--output", str(tmp_path / "doctor.json")])

    assert exit_code == 1
    assert received == [True]


def test_main_forwards_runtime_optional_mode(monkeypatch, tmp_path) -> None:
    received: list[bool | None] = []

    def fake_checks(require_ros=None):
        received.append(require_ros)
        return [CheckResult("runtime", False, "runtime unavailable", blocking=False)]

    monkeypatch.setattr("robotci.doctor_report.run_doctor_checks", fake_checks)

    exit_code = main(["--runtime-optional", "--output", str(tmp_path / "doctor.json")])

    assert exit_code == 0
    assert received == [False]
