import json

from robotci.doctor import CheckResult
from robotci.doctor_report import build_report, main


def test_build_report_passes_with_only_non_blocking_failures(monkeypatch) -> None:
    monkeypatch.delenv("ROBOTCI_ATTEMPT_SCRIPT", raising=False)
    report = build_report(
        [
            CheckResult("platform", True, "supported"),
            CheckResult("docker", False, "not available", blocking=False),
            CheckResult(
                "runtime",
                True,
                "auto runtime will use native ROS2 Jazzy/Nav2",
                value="native",
            ),
        ]
    )

    assert report["schema_version"] == 1
    assert report["status"] == "PASS"
    assert report["runtime"] == {
        "ok": True,
        "selected": "native",
        "message": "auto runtime will use native ROS2 Jazzy/Nav2",
        "adapter_override": False,
    }


def test_build_report_reports_adapter_override_without_path(monkeypatch) -> None:
    adapter_path = "/private/company/robotci_adapter.sh"
    monkeypatch.setenv("ROBOTCI_ATTEMPT_SCRIPT", adapter_path)

    report = build_report(
        [
            CheckResult(
                "runtime",
                True,
                "auto runtime will use native ROS2 Jazzy/Nav2",
                value="native",
            )
        ]
    )
    payload = json.dumps(report)

    assert report["runtime"]["adapter_override"] is True
    assert adapter_path not in payload
    assert "robotci_adapter.sh" not in payload


def test_build_report_fails_on_blocking_failure(monkeypatch) -> None:
    monkeypatch.delenv("ROBOTCI_ATTEMPT_SCRIPT", raising=False)
    report = build_report(
        [
            CheckResult("platform", True, "supported"),
            CheckResult("runtime", False, "no usable runtime found", value="none"),
        ]
    )

    assert report["status"] == "FAIL"
    assert report["runtime"]["selected"] == "none"
    assert report["runtime"]["adapter_override"] is False
    assert report["checks"][1]["blocking"] is True


def test_main_writes_json_and_returns_success(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("ROBOTCI_ATTEMPT_SCRIPT", raising=False)
    monkeypatch.setattr(
        "robotci.doctor_report.run_doctor_checks",
        lambda require_ros=None: [
            CheckResult("platform", True, "supported"),
            CheckResult("runtime", True, "auto runtime will use Docker", value="docker"),
        ],
    )
    output = tmp_path / "diagnostics" / "doctor.json"

    exit_code = main(["--output", str(output)])

    assert exit_code == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["status"] == "PASS"
    assert report["runtime"]["selected"] == "docker"
    assert report["runtime"]["message"] == "auto runtime will use Docker"
    assert report["runtime"]["adapter_override"] is False


def test_main_forwards_strict_native_mode(monkeypatch, tmp_path) -> None:
    received: list[bool | None] = []

    def fake_checks(require_ros=None):
        received.append(require_ros)
        return [CheckResult("runtime", False, "native runtime incomplete", value="none")]

    monkeypatch.setattr("robotci.doctor_report.run_doctor_checks", fake_checks)

    exit_code = main(["--require-ros", "--output", str(tmp_path / "doctor.json")])

    assert exit_code == 1
    assert received == [True]


def test_main_forwards_runtime_optional_mode(monkeypatch, tmp_path) -> None:
    received: list[bool | None] = []

    def fake_checks(require_ros=None):
        received.append(require_ros)
        return [
            CheckResult(
                "runtime",
                False,
                "runtime unavailable",
                blocking=False,
                value="none",
            )
        ]

    monkeypatch.setattr("robotci.doctor_report.run_doctor_checks", fake_checks)

    exit_code = main(["--runtime-optional", "--output", str(tmp_path / "doctor.json")])

    assert exit_code == 0
    assert received == [False]
