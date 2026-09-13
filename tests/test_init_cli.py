from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from robotci.config import load_config
from robotci.init_cli import app

runner = CliRunner()


def test_init_cli_creates_config_and_prints_next_steps(tmp_path: Path) -> None:
    result = runner.invoke(app, ["--project-root", str(tmp_path)])

    assert result.exit_code == 0, result.stdout
    config_path = tmp_path / "robotci.yaml"
    assert config_path.is_file()
    assert load_config(config_path).scenarios[0].name == "smoke_route"
    assert "Created" in result.stdout
    assert "robotci validate --config" in result.stdout
    assert "robotci doctor" in result.stdout
    assert "robotci run --config" in result.stdout


def test_init_cli_requires_force_to_replace_existing_config(tmp_path: Path) -> None:
    first = runner.invoke(app, ["--project-root", str(tmp_path)])
    duplicate = runner.invoke(app, ["--project-root", str(tmp_path)])
    replaced = runner.invoke(app, ["--project-root", str(tmp_path), "--force"])

    assert first.exit_code == 0, first.stdout
    assert duplicate.exit_code == 3
    assert "already exists" in duplicate.stdout
    assert replaced.exit_code == 0, replaced.stdout
    assert "Replaced" in replaced.stdout


def test_init_cli_reports_missing_project_root(tmp_path: Path) -> None:
    missing = tmp_path / "missing"

    result = runner.invoke(app, ["--project-root", str(missing)])

    assert result.exit_code != 0
    assert not (missing / "robotci.yaml").exists()
