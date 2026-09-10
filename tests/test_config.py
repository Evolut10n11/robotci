from pathlib import Path

import pytest

from robotci.config import ConfigError, load_config


def test_load_config_reads_valid_robotci_yaml(tmp_path: Path) -> None:
    config_path = tmp_path / "robotci.yaml"

    config_path.write_text(
        """
version: 1
runtime: docker

scenarios:
  - name: test_route
    start:
      x: 0.0
      y: 0.0
      yaw: 0.0
    goal:
      x: 4.0
      y: -0.17
      yaw: 0.5
    timeout_sec: 45
""".strip(),
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.version == 1
    assert config.runtime == "docker"
    assert len(config.scenarios) == 1

    scenario = config.scenarios[0]

    assert scenario.name == "test_route"
    assert scenario.start.x == 0.0
    assert scenario.start.y == 0.0
    assert scenario.start.yaw == 0.0
    assert scenario.goal.x == 4.0
    assert scenario.goal.y == -0.17
    assert scenario.goal.yaw == 0.5
    assert scenario.timeout_sec == 45.0


def test_load_config_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="config not found"):
        load_config(tmp_path / "robotci.yaml")


def test_load_config_rejects_unknown_version(tmp_path: Path) -> None:
    config_path = tmp_path / "robotci.yaml"

    config_path.write_text(
        """
version: 999
runtime: auto
scenarios: []
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="version must be 1"):
        load_config(config_path)


def test_load_config_rejects_invalid_runtime(tmp_path: Path) -> None:
    config_path = tmp_path / "robotci.yaml"

    config_path.write_text(
        """
version: 1
runtime: windows

scenarios:
  - name: route
    start:
      x: 0
      y: 0
    goal:
      x: 1
      y: 1
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="runtime must be one of"):
        load_config(config_path)


def test_load_config_rejects_duplicate_scenario_names(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "robotci.yaml"

    config_path.write_text(
        """
version: 1
runtime: auto

scenarios:
  - name: route
    start:
      x: 0
      y: 0
    goal:
      x: 1
      y: 1

  - name: route
    start:
      x: 0
      y: 0
    goal:
      x: 2
      y: 2
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="scenario names must be unique"):
        load_config(config_path)


def test_load_config_rejects_non_positive_timeout(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "robotci.yaml"

    config_path.write_text(
        """
version: 1

scenarios:
  - name: route
    start:
      x: 0
      y: 0
    goal:
      x: 1
      y: 1
    timeout_sec: 0
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="timeout_sec must be greater than zero"):
        load_config(config_path)