from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

import robotci.cli as cli
from robotci.config import ConfigError
from robotci.plan import build_execution_plan

runner = CliRunner()


def _write_config(path: Path) -> None:
    path.write_text(
        """
version: 1
runtime: docker
scenarios:
  - name: smoke
    start: {x: 0, y: 0}
    goal: {x: 1, y: 2}
    timeout_sec: 10
  - name: long_route
    start: {x: 1, y: 2, yaw: 0.5}
    goal: {x: 5, y: 8, yaw: 1.0}
    timeout_sec: 30
""".strip(),
        encoding="utf-8",
    )


def _make_project_root(path: Path) -> Path:
    scripts = path / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "run_navigation_scenario.sh").write_text("#!/usr/bin/env bash\n")
    (path / "pyproject.toml").write_text("[project]\nname = 'robotci-test'\n")
    return path


def test_build_execution_plan_uses_config_defaults(tmp_path: Path) -> None:
    config_path = tmp_path / "robotci.yaml"
    _write_config(config_path)

    plan = build_execution_plan(config_path=config_path)

    assert plan.runtime == "docker"
    assert [scenario.name for scenario in plan.scenarios] == ["smoke", "long_route"]
    assert [scenario.timeout_sec for scenario in plan.scenarios] == [10.0, 30.0]


def test_build_execution_plan_applies_overrides_without_runtime_probe(tmp_path: Path) -> None:
    config_path = tmp_path / "robotci.yaml"
    _write_config(config_path)

    plan = build_execution_plan(
        config_path=config_path,
        scenario="long_route",
        runtime="native",
        timeout_sec=12.5,
    )

    assert plan.runtime == "native"
    assert len(plan.scenarios) == 1
    assert plan.scenarios[0].name == "long_route"
    assert plan.scenarios[0].timeout_sec == 12.5
    assert plan.scenarios[0].start.yaw == 0.5


def test_build_execution_plan_resolves_default_config_from_project_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_root = _make_project_root(tmp_path / "checkout")
    _write_config(project_root / "robotci.yaml")
    nested = project_root / "src" / "nested"
    nested.mkdir(parents=True)
    monkeypatch.chdir(nested)

    plan = build_execution_plan()

    assert plan.runtime == "docker"
    assert [scenario.name for scenario in plan.scenarios] == ["smoke", "long_route"]


@pytest.mark.parametrize("timeout_sec", [float("nan"), float("inf"), float("-inf"), 0.0, -1.0])
def test_build_execution_plan_rejects_invalid_timeout_override(
    tmp_path: Path,
    timeout_sec: float,
) -> None:
    config_path = tmp_path / "robotci.yaml"
    _write_config(config_path)

    with pytest.raises(ConfigError, match="finite number greater than zero"):
        build_execution_plan(config_path=config_path, timeout_sec=timeout_sec)


def test_build_execution_plan_rejects_unknown_scenario(tmp_path: Path) -> None:
    config_path = tmp_path / "robotci.yaml"
    _write_config(config_path)

    with pytest.raises(ConfigError, match="unknown scenario 'missing'"):
        build_execution_plan(config_path=config_path, scenario="missing")


def test_plan_command_prints_human_readable_dry_run(tmp_path: Path) -> None:
    config_path = tmp_path / "robotci.yaml"
    _write_config(config_path)

    result = runner.invoke(
        cli.app,
        [
            "plan",
            "--config",
            str(config_path),
            "--scenario",
            "smoke",
            "--runtime",
            "native",
            "--timeout-sec",
            "15",
        ],
    )

    assert result.exit_code == 0
    assert "Runtime request" in result.stdout
    assert "native" in result.stdout
    assert "smoke" in result.stdout
    assert "15s" in result.stdout
    assert "no runtime started" in result.stdout


def test_plan_command_prints_machine_readable_json(tmp_path: Path) -> None:
    config_path = tmp_path / "robotci.yaml"
    _write_config(config_path)

    result = runner.invoke(
        cli.app,
        ["plan", "--config", str(config_path), "--scenario", "smoke", "--json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload == {
        "runtime": "docker",
        "scenarios": [
            {
                "name": "smoke",
                "start": {"x": 0.0, "y": 0.0, "yaw": 0.0},
                "goal": {"x": 1.0, "y": 2.0, "yaw": 0.0},
                "timeout_sec": 10.0,
            }
        ],
    }
