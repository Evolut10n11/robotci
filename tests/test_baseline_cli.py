from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from robotci.baseline_cli import app

runner = CliRunner()
FIXTURE = Path(__file__).parent / "fixtures" / "gate-suite" / "baseline" / "suite-result.json"


def test_save_and_show_baseline_as_json(tmp_path: Path) -> None:
    store = tmp_path / "baselines"

    saved = runner.invoke(
        app,
        [
            "save",
            "known-good",
            "--suite",
            str(FIXTURE),
            "--store",
            str(store),
            "--json",
        ],
    )

    assert saved.exit_code == 0, saved.stdout
    saved_payload = json.loads(saved.stdout)
    assert saved_payload["name"] == "known-good"
    assert saved_payload["scenarios"] == ["route"]
    assert Path(saved_payload["suite_file"]).is_file()

    shown = runner.invoke(
        app,
        ["show", "known-good", "--store", str(store), "--json"],
    )

    assert shown.exit_code == 0, shown.stdout
    shown_payload = json.loads(shown.stdout)
    assert shown_payload == saved_payload


def test_list_baselines_returns_sorted_machine_readable_metadata(tmp_path: Path) -> None:
    store = tmp_path / "baselines"
    for name in ("zeta", "alpha"):
        result = runner.invoke(
            app,
            ["save", name, "--suite", str(FIXTURE), "--store", str(store)],
        )
        assert result.exit_code == 0, result.stdout

    listed = runner.invoke(app, ["list", "--store", str(store), "--json"])

    assert listed.exit_code == 0, listed.stdout
    payload = json.loads(listed.stdout)
    assert [item["name"] for item in payload] == ["alpha", "zeta"]
    assert all(item["scenarios"] == ["route"] for item in payload)
    assert all(item["captured_at"] for item in payload)
    assert all(item["source_suite"].endswith("suite-result.json") for item in payload)


def test_save_requires_explicit_replace_for_existing_baseline(tmp_path: Path) -> None:
    store = tmp_path / "baselines"
    args = ["save", "stable", "--suite", str(FIXTURE), "--store", str(store)]

    first = runner.invoke(app, args)
    duplicate = runner.invoke(app, args)
    replaced = runner.invoke(app, [*args, "--replace"])

    assert first.exit_code == 0, first.stdout
    assert duplicate.exit_code == 3
    assert "baseline already exists: stable" in duplicate.stdout
    assert replaced.exit_code == 0, replaced.stdout


def test_remove_deletes_baseline(tmp_path: Path) -> None:
    store = tmp_path / "baselines"
    saved = runner.invoke(
        app,
        ["save", "temporary", "--suite", str(FIXTURE), "--store", str(store)],
    )
    assert saved.exit_code == 0, saved.stdout

    removed = runner.invoke(app, ["remove", "temporary", "--store", str(store)])
    shown = runner.invoke(app, ["show", "temporary", "--store", str(store)])

    assert removed.exit_code == 0, removed.stdout
    assert "Removed baseline temporary" in removed.stdout
    assert shown.exit_code == 3
    assert "does not exist" in shown.stdout


def test_list_empty_store_is_successful(tmp_path: Path) -> None:
    listed = runner.invoke(app, ["list", "--store", str(tmp_path / "missing")])

    assert listed.exit_code == 0
    assert "No baselines found." in listed.stdout
