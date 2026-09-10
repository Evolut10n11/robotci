from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

import robotci.cli as cli
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
        return 0, "docker", result_path

    monkeypatch.setattr(cli, "run_scenario", fake_run_scenario)

    result = runner.invoke(
        cli.app,
        ["run", "--runtime", "docker", "--output", str(result_path)],
    )

    assert result.exit_code == 0
    assert "docker" in result.stdout
    assert "PASS" in result.stdout
    normalized_stdout = result.stdout.replace("\r", "").replace("\n", "")
    assert str(result_path) in normalized_stdout


def test_run_command_returns_infra_error_when_runtime_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run_scenario(**kwargs: object) -> tuple[int, str, Path]:
        raise RuntimeUnavailableError("Docker daemon is unavailable")

    monkeypatch.setattr(cli, "run_scenario", fake_run_scenario)

    result = runner.invoke(cli.app, ["run", "--runtime", "docker"])

    assert result.exit_code == 3
    assert "Docker daemon is unavailable" in result.stdout
