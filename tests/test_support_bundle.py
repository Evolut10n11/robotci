import json
from pathlib import Path

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
        CheckResult("runtime", True, "auto runtime will use Docker"),
    ]


def test_bundle_omits_paths_names_and_environment_variables(tmp_path: Path, monkeypatch) -> None:
    config = tmp_path / "secret-project" / "robotci.yaml"
    config.parent.mkdir()
    _write_config(config)
    monkeypatch.setattr("robotci.support_bundle.run_doctor_checks", lambda **_: _passing_checks())

    bundle = build_support_bundle(config_path=config)
    payload = json.dumps(bundle)

    assert bundle["status"] == "PASS"
    assert bundle["config"] == {
        "status": "PASS",
        "runtime": "auto",
        "scenario_count": 1,
        "error": None,
    }
    assert "confidential_route" not in payload
    assert "secret-project" not in payload
    assert bundle["privacy"] == {
        "includes_project_paths": False,
        "includes_scenario_names": False,
        "includes_environment_variables": False,
        "includes_credentials": False,
    }


def test_bundle_redacts_invalid_config_details(tmp_path: Path, monkeypatch) -> None:
    config = tmp_path / "secret-project" / "robotci.yaml"
    config.parent.mkdir()
    config.write_text("version: 1\nruntime: auto\nscenarios: []\n", encoding="utf-8")
    monkeypatch.setattr("robotci.support_bundle.run_doctor_checks", lambda **_: _passing_checks())

    bundle = build_support_bundle(config_path=config)
    payload = json.dumps(bundle)

    assert bundle["status"] == "FAIL"
    assert bundle["config"]["status"] == "FAIL"
    assert bundle["config"]["error"] == (
        "RobotCI config is invalid; run 'robotci validate' locally for details"
    )
    assert "secret-project" not in payload


def test_bundle_redacts_missing_config_path(tmp_path: Path, monkeypatch) -> None:
    config = tmp_path / "private-company-repo" / "robotci.yaml"
    monkeypatch.setattr("robotci.support_bundle.run_doctor_checks", lambda **_: _passing_checks())

    bundle = build_support_bundle(config_path=config)
    payload = json.dumps(bundle)

    assert bundle["status"] == "FAIL"
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
