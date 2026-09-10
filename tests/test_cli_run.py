from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

import robotci.cli as cli
from robotci.config import ConfigError
from robotci.runner import RuntimeUnavailableError

runner = CliRunner()


def test_run_command_reports_selected_runtime_and_verdict(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result_path = tmp_path / "result.json"
    result_path.write_text('{"status": "PASS"}\n', encoding="utf-8")

    def fake_run_scenario(**kwargs: object) -> tuple[int, str, Path]:
        assert kwargs["scenario"] == "simple_route"
        assert kwargs["runtime"] == "docker"
        assert kwargs["config_path"] == Path("robotci.yaml")
        return 0, "docker", result_path

    monkeypatch.setattr(cli, "run_scenario", fake_run_scenario)

    result = runner.invoke(
        cli.app,
        [
            "run",
            "--runtime",
            "docker",
            "--scenario",
            "simple_route",
            "--output",
            str(result_path),
        ],
    )

    assert result.exit_code == 0
    assert "docker" in result.stdout
    assert "PASS" in result.stdout
    normalized_stdout = result.stdout.replace("\r", "").replace("\n", "")
    assert str(result_path) in normalized_stdout


def test_run_command_runs_suite_when_scenario_is_omitted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    suite_path = tmp_path / "suite-result.json"
    suite_path.write_text('{"status": "PASS"}\n', encoding="utf-8")

    def fake_run_suite(**kwargs: object) -> tuple[int, str, Path]:
        assert kwargs["runtime"] == "native"
        assert kwargs["config_path"] == Path("robotci.yaml")
        return 0, "native", suite_path

    monkeypatch.setattr(cli, "run_suite", fake_run_suite)

    result = runner.invoke(cli.app, ["run", "--runtime", "native", "--output", str(suite_path)])

    assert result.exit_code == 0
    assert "Suite verdict" in result.stdout
    assert "PASS" in result.stdout


def test_run_command_leaves_runtime_to_yaml_when_not_overridden(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    suite_path = tmp_path / "suite-result.json"
    suite_path.write_text('{"status": "PASS"}\n', encoding="utf-8")

    def fake_run_suite(**kwargs: object) -> tuple[int, str, Path]:
        assert kwargs["runtime"] is None
        return 0, "native", suite_path

    monkeypatch.setattr(cli, "run_suite", fake_run_suite)

    result = runner.invoke(cli.app, ["run", "--output", str(suite_path)])

    assert result.exit_code == 0


def test_run_command_returns_config_error_cleanly(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run_suite(**kwargs: object) -> tuple[int, str, Path]:
        raise ConfigError("config.version must be 1")

    monkeypatch.setattr(cli, "run_suite", fake_run_suite)

    result = runner.invoke(cli.app, ["run"])

    assert result.exit_code == 3
    assert "RobotCI config error" in result.stdout
    assert "config.version must be 1" in result.stdout


def test_run_command_returns_infra_error_when_runtime_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run_suite(**kwargs: object) -> tuple[int, str, Path]:
        raise RuntimeUnavailableError("Docker daemon is unavailable")

    monkeypatch.setattr(cli, "run_suite", fake_run_suite)

    result = runner.invoke(cli.app, ["run", "--runtime", "docker"])

    assert result.exit_code == 3
    assert "Docker daemon is unavailable" in result.stdout


def test_validate_command_reports_valid_config(tmp_path: Path) -> None:
    config_path = tmp_path / "robotci.yaml"
    config_path.write_text(
        """
version: 1
runtime: auto
scenarios:
  - name: smoke
    start: {x: 0, y: 0}
    goal: {x: 1, y: 1}
    timeout_sec: 10
""".strip(),
        encoding="utf-8",
    )

    result = runner.invoke(cli.app, ["validate", "--config", str(config_path)])

    assert result.exit_code == 0
    assert "Configuration valid" in result.stdout
    assert "smoke" in result.stdout
    assert "10s" in result.stdout


def test_validate_command_reports_invalid_config(tmp_path: Path) -> None:
    config_path = tmp_path / "robotci.yaml"
    config_path.write_text("version: 2\nscenarios: []\n", encoding="utf-8")

    result = runner.invoke(cli.app, ["validate", "--config", str(config_path)])

    assert result.exit_code == 3
    assert "RobotCI config error" in result.stdout
