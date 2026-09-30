from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

import robotci.cli as cli
from robotci.application import DiagnosticReport, ProjectInfo, RobotCIApplication
from robotci.doctor import CheckResult

runner = CliRunner()


def test_validate_command_routes_through_application(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "robotci.yaml"
    config_path.write_text(
        """\
version: 1
runtime: auto
scenarios:
  - name: application_route
    start: {x: 0, y: 0}
    goal: {x: 1, y: 1}
    timeout_sec: 10
""",
        encoding="utf-8",
    )
    original = RobotCIApplication.get_project_info
    calls: list[Path] = []

    def tracked_get_project_info(self: RobotCIApplication) -> ProjectInfo:
        calls.append(self.context.config_path)
        return original(self)

    monkeypatch.setattr(RobotCIApplication, "get_project_info", tracked_get_project_info)

    result = runner.invoke(cli.app, ["validate", "--config", str(config_path)])

    assert result.exit_code == 0
    assert calls == [config_path.resolve()]
    assert "application_route" in result.stdout
    assert "Configuration valid" in result.stdout


def test_doctor_command_routes_through_application(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[bool | None] = []

    def fake_get_diagnostics(
        self: RobotCIApplication,
        *,
        require_ros: bool | None = None,
    ) -> DiagnosticReport:
        calls.append(require_ros)
        return DiagnosticReport(
            (
                CheckResult("platform", True, "supported"),
                CheckResult("runtime", False, "no runtime", blocking=True),
            )
        )

    monkeypatch.setattr(RobotCIApplication, "get_diagnostics", fake_get_diagnostics)

    result = runner.invoke(cli.app, ["doctor"])

    assert result.exit_code == 1
    assert calls == [None]
    assert "platform" in result.stdout
    assert "runtime" in result.stdout
    assert "FAIL" in result.stdout
