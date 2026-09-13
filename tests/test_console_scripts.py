import tomllib
from pathlib import Path


def test_pilot_console_scripts_are_packaged() -> None:
    pyproject = Path(__file__).parents[1] / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    scripts = data["project"]["scripts"]

    assert scripts["robotci-doctor"] == "robotci.doctor_report:main"
    assert scripts["robotci-support-bundle"] == "robotci.support_bundle:main"
