from __future__ import annotations

import tomllib
from pathlib import Path

from robotci import __version__


def test_public_alpha_version_matches_project_metadata() -> None:
    pyproject = Path(__file__).parents[1] / "pyproject.toml"
    project = tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]

    assert __version__ == "0.1.0a1"
    assert project["version"] == __version__
    assert "Development Status :: 3 - Alpha" in project["classifiers"]
