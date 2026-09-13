from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from robotci.suite_cli import app

runner = CliRunner()


def _write_result(
    path: Path,
    *,
    scenario: str,
    duration_sec: float,
    path_length_m: float,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "scenario": scenario,
                "status": "PASS",
                "duration_sec": duration_sec,
                "metrics": {
                    "path_length_m": path_length_m,
                    "distance_to_goal_m": 0.1,
                    "stuck_events": 0,
                    "feedback_samples": 10,
                    "recoveries": 0,
                },
            }
        ),
        encoding="utf-8",
    )


def _write_suite(root: Path, *, duration: float, path_length: float) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    result = root / "results" / "route.json"
    _write_result(
        result,
        scenario="route",
        duration_sec=duration,
        path_length_m=path_length,
    )
    suite = root / "suite-result.json"
    suite.write_text(
        json.dumps(
            {
                "status": "PASS",
                "runtime": "native",
                "duration_sec": duration,
                "scenarios": [
                    {
                        "scenario": "route",
                        "status": "PASS",
                        "duration_sec": duration,
                        "result_file": "results/route.json",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return suite


def test_suite_gate_writes_report_before_regression_exit(tmp_path: Path) -> None:
    baseline = _write_suite(tmp_path / "baseline", duration=10.0, path_length=5.0)
    candidate = _write_suite(tmp_path / "candidate", duration=12.0, path_length=6.0)
    output = tmp_path / "artifacts" / "suite-regression.json"

    result = runner.invoke(
        app,
        [
            "--baseline",
            str(baseline),
            "--candidate",
            str(candidate),
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 4
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["kind"] == "suite_regression"
    assert payload["status"] == "REGRESSION"
    assert payload["scenarios"][0]["status"] == "REGRESSION"


def test_suite_gate_writes_markdown_before_regression_exit(tmp_path: Path) -> None:
    baseline = _write_suite(tmp_path / "baseline", duration=10.0, path_length=5.0)
    candidate = _write_suite(tmp_path / "candidate", duration=12.0, path_length=6.0)
    summary = tmp_path / "artifacts" / "suite-regression.md"

    result = runner.invoke(
        app,
        [
            "--baseline",
            str(baseline),
            "--candidate",
            str(candidate),
            "--markdown-output",
            str(summary),
        ],
    )

    assert result.exit_code == 4
    markdown = summary.read_text(encoding="utf-8")
    assert "## RobotCI suite regression gate" in markdown
    assert "❌ **REGRESSION**" in markdown
    assert "| `route` | ❌ REGRESSION |" in markdown
    assert "`duration_sec`" in markdown
    assert "`path_length_m`" in markdown
    assert "### Policy" in markdown


def test_suite_gate_json_output_is_strict_for_zero_baseline(tmp_path: Path) -> None:
    baseline = _write_suite(tmp_path / "baseline", duration=0.0, path_length=0.0)
    candidate = _write_suite(tmp_path / "candidate", duration=1.0, path_length=1.0)

    result = runner.invoke(
        app,
        [
            "--baseline",
            str(baseline),
            "--candidate",
            str(candidate),
            "--json",
        ],
    )

    assert result.exit_code == 4
    payload = json.loads(result.stdout)
    findings = payload["scenarios"][0]["findings"]
    assert all(item["increase"] is None for item in findings)
    assert all(item["increase_unbounded"] is True for item in findings)
