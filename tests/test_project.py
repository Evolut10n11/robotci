from __future__ import annotations

from pathlib import Path

from robotci.project import resolve_project_context


def _write_config(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("version: 1\nscenarios: []\n", encoding="utf-8")
    return path


def test_default_config_anchors_context_to_external_project(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project = tmp_path / "external-project"
    config = _write_config(project / "robotci.yaml")
    monkeypatch.chdir(project)

    context = resolve_project_context()

    assert context.project_root == project.resolve()
    assert context.config_path == config.resolve()


def test_default_config_is_found_from_nested_project_directory(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project = tmp_path / "external-project"
    config = _write_config(project / "robotci.yaml")
    nested = project / "src" / "navigation"
    nested.mkdir(parents=True)
    monkeypatch.chdir(nested)

    context = resolve_project_context()

    assert context.project_root == project.resolve()
    assert context.config_path == config.resolve()


def test_absolute_config_defines_project_root(tmp_path: Path) -> None:
    config = _write_config(tmp_path / "pilot" / "robotci.yaml")

    context = resolve_project_context(config)

    assert context.project_root == config.parent.resolve()
    assert context.config_path == config.resolve()


def test_explicit_project_root_anchors_relative_config(tmp_path: Path) -> None:
    project = tmp_path / "pilot"
    config = _write_config(project / "config" / "robotci.yaml")

    context = resolve_project_context(
        Path("config") / "robotci.yaml",
        project_root=project,
    )

    assert context.project_root == project.resolve()
    assert context.config_path == config.resolve()


def test_missing_config_does_not_fall_back_to_package_checkout(
    tmp_path: Path,
    monkeypatch,
) -> None:
    project = tmp_path / "empty-project"
    project.mkdir()
    monkeypatch.chdir(project)

    context = resolve_project_context()

    assert context.project_root == project.resolve()
    assert context.config_path == (project / "robotci.yaml").resolve()
