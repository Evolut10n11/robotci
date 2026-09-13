from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from robotci.baseline_cli import app

runner = CliRunner()
FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "gate-suite"
FIXTURE = FIXTURE_ROOT / "baseline" / "suite-result.json"
PASS_FIXTURE = FIXTURE_ROOT / "pass" / "suite-result.json"
REGRESSION_FIXTURE = FIXTURE_ROOT / "regression" / "suite-result.json"


def _save_baseline(store: Path, name: str = "known-good") -> None:
    saved = runner.invoke(
        app,
        ["save", name, "--suite", str(FIXTURE), "--store", str(store)],
    )
    assert saved.exit_code == 0, saved.stdout


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


def test_gate_saved_baseline_passes_for_stable_candidate(tmp_path: Path) -> None:
    store = tmp_path / "baselines"
    _save_baseline(store, "stable")

    result = runner.invoke(
        app,
        [
            "gate",
            "stable",
            "--candidate",
            str(PASS_FIXTURE),
            "--store",
            str(store),
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert "Suite regression verdict: PASS" in result.stdout
    assert "Baseline: stable" in result.stdout


def test_gate_saved_baseline_returns_regression_exit_code(tmp_path: Path) -> None:
    store = tmp_path / "baselines"
    _save_baseline(store, "stable")

    result = runner.invoke(
        app,
        [
            "gate",
            "stable",
            "--candidate",
            str(REGRESSION_FIXTURE),
            "--store",
            str(store),
        ],
    )

    assert result.exit_code == 4
    assert "Suite regression verdict: REGRESSION" in result.stdout


def test_gate_missing_saved_baseline_returns_input_error(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "gate",
            "missing",
            "--candidate",
            str(PASS_FIXTURE),
            "--store",
            str(tmp_path / "baselines"),
        ],
    )

    assert result.exit_code == 3
    assert "baseline manifest does not exist" in result.stdout


def test_gate_saved_baseline_writes_all_report_formats(tmp_path: Path) -> None:
    store = tmp_path / "baselines"
    _save_baseline(store, "stable")
    report = tmp_path / "artifacts" / "regression.json"
    markdown = tmp_path / "artifacts" / "regression.md"
    junit = tmp_path / "artifacts" / "regression.xml"

    result = runner.invoke(
        app,
        [
            "gate",
            "stable",
            "--candidate",
            str(REGRESSION_FIXTURE),
            "--store",
            str(store),
            "--json",
            "--output",
            str(report),
            "--markdown-output",
            str(markdown),
            "--junit-output",
            str(junit),
        ],
    )

    assert result.exit_code == 4
    payload = json.loads(result.stdout)
    assert payload["status"] == "REGRESSION"
    assert json.loads(report.read_text(encoding="utf-8"))["status"] == "REGRESSION"
    assert "RobotCI suite regression gate" in markdown.read_text(encoding="utf-8")
    assert "<testsuite" in junit.read_text(encoding="utf-8")


def test_gate_saved_baseline_honors_threshold_overrides(tmp_path: Path) -> None:
    store = tmp_path / "baselines"
    _save_baseline(store, "stable")

    result = runner.invoke(
        app,
        [
            "gate",
            "stable",
            "--candidate",
            str(REGRESSION_FIXTURE),
            "--store",
            str(store),
            "--max-duration-increase-pct",
            "100",
            "--max-path-length-increase-pct",
            "100",
            "--max-stuck-events-increase",
            "100",
            "--max-recoveries-increase",
            "100",
        ],
    )

    assert result.exit_code == 0, result.stdout
    assert "Suite regression verdict: PASS" in result.stdout


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
