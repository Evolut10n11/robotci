import json
from pathlib import Path

from robotci.config import ConfigError
from robotci.doctor import CheckResult
from robotci.support_bundle import build_support_bundle, main


def _write_config(path: Path, *, runtime: str = "auto") -> None:
    path.write_text(
        "\n".join(
            [
                "version: 1",
                f"runtime: {runtime}",
                "scenarios:",
                "  - name: confidential_route",
                "    start: {x: 0, y: 0}",
                "    goal: {x: 1, y: 1}",
                "    timeout_sec: 30",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _passing_checks() -> list[CheckResult]:
    return [
        CheckResult("platform", True, "platform ready"),
        CheckResult("docker", True, "docker daemon is available", blocking=False),
        CheckResult("runtime", True, "auto runtime will use Docker", value="docker"),
    ]


def test_bundle_omits_paths_names_and_environment_variables(tmp_path: Path, monkeypatch) -> None:
    config = tmp_path / "secret-project" / "robotci.yaml"
    config.parent.mkdir()
    _write_config(config)
    monkeypatch.delenv("ROBOTCI_ATTEMPT_SCRIPT", raising=False)
    monkeypatch.setattr("robotci.support_bundle.run_doctor_checks", lambda **_: _passing_checks())

    bundle = build_support_bundle(config_path=config)
    payload = json.dumps(bundle)

    assert bundle["status"] == "PASS"
    assert bundle["config"] == {
        "status": "PASS",
        "runtime": "auto",
        "scenario_count": 1,
        "error_code": None,
        "error": None,
    }
    assert bundle["doctor"]["runtime"]["adapter_override"] is False
    assert "confidential_route" not in payload
    assert "secret-project" not in payload
    assert bundle["privacy"] == {
        "includes_project_paths": False,
        "includes_scenario_names": False,
        "includes_environment_variables": False,
        "includes_credentials": False,
    }


def test_bundle_reports_adapter_override_without_leaking_path(tmp_path: Path, monkeypatch) -> None:
    config = tmp_path / "robotci.yaml"
    _write_config(config)
    adapter_path = "/private-company-repo/scripts/robotci_adapter.sh"
    monkeypatch.setenv("ROBOTCI_ATTEMPT_SCRIPT", adapter_path)
    monkeypatch.setattr("robotci.support_bundle.run_doctor_checks", lambda **_: _passing_checks())

    bundle = build_support_bundle(config_path=config)
    payload = json.dumps(bundle)

    assert bundle["doctor"]["runtime"]["adapter_override"] is True
    assert adapter_path not in payload
    assert "private-company-repo" not in payload
    assert "robotci_adapter.sh" not in payload


def test_bundle_redacts_ros_package_prefixes(tmp_path: Path, monkeypatch) -> None:
    config = tmp_path / "robotci.yaml"
    _write_config(config)
    checks = [
        CheckResult("platform", True, "Linux: RobotCI core and ROS runtime supported"),
        CheckResult("nav2_bringup", True, "installed at /opt/ros/jazzy"),
        CheckResult("nav2_loopback_sim", True, "installed at /private/runtime/nav2_loopback_sim"),
        CheckResult("nav2_simple_commander", True, "installed at /srv/robot/ros/jazzy"),
        CheckResult("runtime", True, "auto runtime will use native ROS2 Jazzy/Nav2"),
    ]
    monkeypatch.setattr("robotci.support_bundle.run_doctor_checks", lambda **_: checks)

    bundle = build_support_bundle(config_path=config)
    payload = json.dumps(bundle)
    package_checks = {
        check["name"]: check["message"]
        for check in bundle["doctor"]["checks"]
        if check["name"].startswith("nav2_")
    }

    assert package_checks == {
        "nav2_bringup": "package is installed",
        "nav2_loopback_sim": "package is installed",
        "nav2_simple_commander": "package is installed",
    }
    assert "/opt/ros/jazzy" not in payload
    assert "/private/runtime/nav2_loopback_sim" not in payload
    assert "/srv/robot/ros/jazzy" not in payload


def test_bundle_redacts_invalid_config_details(tmp_path: Path, monkeypatch) -> None:
    config = tmp_path / "secret-project" / "robotci.yaml"
    config.parent.mkdir()
    config.write_text("version: 1\nruntime: auto\nscenarios: []\n", encoding="utf-8")
    monkeypatch.setattr("robotci.support_bundle.run_doctor_checks", lambda **_: _passing_checks())

    bundle = build_support_bundle(config_path=config)
    payload = json.dumps(bundle)

    assert bundle["status"] == "FAIL"
    assert bundle["config"]["status"] == "FAIL"
    assert bundle["config"]["error_code"] == "config_invalid"
    assert bundle["config"]["error"] == (
        "RobotCI config is invalid; run 'robotci validate' locally for details"
    )
    assert "secret-project" not in payload


def test_bundle_classifies_unreadable_config_without_leaking_details(
    tmp_path: Path, monkeypatch
) -> None:
    config = tmp_path / "private-company-repo" / "robotci.yaml"
    config.parent.mkdir()
    _write_config(config)
    monkeypatch.setattr("robotci.support_bundle.run_doctor_checks", lambda **_: _passing_checks())

    def unreadable_config(_path: Path):
        try:
            raise OSError("permission denied at /private-company-repo/robotci.yaml")
        except OSError as exc:
            raise ConfigError("failed to read secret path") from exc

    monkeypatch.setattr("robotci.support_bundle.load_config", unreadable_config)

    bundle = build_support_bundle(config_path=config)
    payload = json.dumps(bundle)

    assert bundle["status"] == "FAIL"
    assert bundle["config"]["error_code"] == "config_unreadable"
    assert bundle["config"]["error"] == (
        "RobotCI config could not be read; check file access locally and retry"
    )
    assert "private-company-repo" not in payload
    assert "permission denied" not in payload
    assert "secret path" not in payload


def test_bundle_redacts_missing_config_path(tmp_path: Path, monkeypatch) -> None:
    config = tmp_path / "private-company-repo" / "robotci.yaml"
    monkeypatch.setattr("robotci.support_bundle.run_doctor_checks", lambda **_: _passing_checks())

    bundle = build_support_bundle(config_path=config)
    payload = json.dumps(bundle)

    assert bundle["status"] == "FAIL"
    assert bundle["config"]["error_code"] == "config_not_found"
    assert bundle["config"]["error"] == (
        "RobotCI config is invalid; run 'robotci validate' locally for details"
    )
    assert "private-company-repo" not in payload
    assert str(config) not in payload


def test_bundle_fails_when_runtime_is_not_ready(tmp_path: Path, monkeypatch) -> None:
    config = tmp_path / "robotci.yaml"
    _write_config(config)
    checks = [
        CheckResult("platform", True, "platform ready"),
        CheckResult("runtime", False, "no usable runtime found"),
    ]
    monkeypatch.setattr("robotci.support_bundle.run_doctor_checks", lambda **_: checks)

    bundle = build_support_bundle(config_path=config)

    assert bundle["status"] == "FAIL"
    assert bundle["doctor"]["status"] == "FAIL"


def test_runtime_optional_allows_inventory_bundle(tmp_path: Path, monkeypatch) -> None:
    config = tmp_path / "robotci.yaml"
    output = tmp_path / "support.json"
    _write_config(config)
    seen: dict[str, bool | None] = {}

    def fake_checks(*, require_ros: bool | None = None) -> list[CheckResult]:
        seen["require_ros"] = require_ros
        return [CheckResult("runtime", False, "inventory only", blocking=False)]

    monkeypatch.setattr("robotci.support_bundle.run_doctor_checks", fake_checks)

    exit_code = main(
        [
            "--config",
            str(config),
            "--output",
            str(output),
            "--runtime-optional",
        ]
    )

    assert exit_code == 0
    assert seen["require_ros"] is False
    assert json.loads(output.read_text(encoding="utf-8"))["status"] == "PASS"


def test_output_dash_writes_bundle_to_stdout(tmp_path: Path, monkeypatch, capsys) -> None:
    config = tmp_path / "robotci.yaml"
    _write_config(config)
    monkeypatch.setattr("robotci.support_bundle.run_doctor_checks", lambda **_: _passing_checks())

    exit_code = main(["--config", str(config), "--output", "-"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert payload["status"] == "PASS"
    assert payload["config"]["scenario_count"] == 1
    assert not (tmp_path / "-").exists()


def test_compact_output_is_single_line_json(tmp_path: Path, monkeypatch, capsys) -> None:
    config = tmp_path / "robotci.yaml"
    _write_config(config)
    monkeypatch.setattr("robotci.support_bundle.run_doctor_checks", lambda **_: _passing_checks())

    exit_code = main(["--config", str(config), "--output", "-", "--compact"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert captured.out.count("\n") == 1
    assert ": " not in captured.out
    assert json.loads(captured.out)["status"] == "PASS"
