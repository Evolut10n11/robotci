from pathlib import Path

from robotci.paths import result_path, state_dir


def test_state_dir_is_relative_to_project_root(tmp_path: Path) -> None:
    assert state_dir(tmp_path) == tmp_path / ".robotci"


def test_result_path_is_inside_state_dir(tmp_path: Path) -> None:
    assert result_path(tmp_path) == tmp_path / ".robotci" / "result.json"


def test_string_project_root_is_supported(tmp_path: Path) -> None:
    assert result_path(str(tmp_path)) == tmp_path / ".robotci" / "result.json"
