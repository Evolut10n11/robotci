from __future__ import annotations

from pathlib import Path

import pytest

from robotci.config import load_config
from robotci.scaffold import ScaffoldError, initialize_project


def test_initialize_project_creates_valid_starter_config(tmp_path: Path) -> None:
    result = initialize_project(tmp_path)

    assert result.project_root == tmp_path.resolve()
    assert result.config_path == tmp_path / "robotci.yaml"
    assert result.replaced is False
    assert result.config_path.is_file()

    config = load_config(result.config_path)
    assert config.version == 1
    assert config.runtime == "auto"
    assert len(config.scenarios) == 1

    scenario = config.scenarios[0]
    assert scenario.name == "smoke_route"
    assert scenario.start.x == 0.0
    assert scenario.start.y == 0.0
    assert scenario.goal.x == 1.0
    assert scenario.goal.y == 0.0
    assert scenario.timeout_sec == 60.0
    assert scenario.map_id == "nav2-loopback"
    assert scenario.goal_tolerance_m == 0.25
    assert scenario.min_feedback_samples == 1
    assert list(tmp_path.glob(".robotci-init-*.yaml")) == []


def test_initialize_project_refuses_accidental_overwrite(tmp_path: Path) -> None:
    config_path = tmp_path / "robotci.yaml"
    config_path.write_text("keep-me\n", encoding="utf-8")

    with pytest.raises(ScaffoldError, match="already exists"):
        initialize_project(tmp_path)

    assert config_path.read_text(encoding="utf-8") == "keep-me\n"


def test_initialize_project_force_replaces_existing_config(tmp_path: Path) -> None:
    config_path = tmp_path / "robotci.yaml"
    config_path.write_text("invalid: true\n", encoding="utf-8")

    result = initialize_project(tmp_path, force=True)

    assert result.replaced is True
    assert load_config(config_path).scenarios[0].name == "smoke_route"


def test_initialize_project_requires_existing_directory(tmp_path: Path) -> None:
    missing = tmp_path / "missing"

    with pytest.raises(ScaffoldError, match="project root does not exist"):
        initialize_project(missing)


def test_initialize_project_rejects_file_as_project_root(tmp_path: Path) -> None:
    file_path = tmp_path / "not-a-directory"
    file_path.write_text("x", encoding="utf-8")

    with pytest.raises(ScaffoldError, match="project root is not a directory"):
        initialize_project(file_path)
