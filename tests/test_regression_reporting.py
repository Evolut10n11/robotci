from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from robotci.cli import app

runner = CliRunner()


def _write_result(
    path: Path,
    *,
    duration_sec: float = 10.0,
    path_length_m: float = 5.0,
) -> None:
    path.write_text(
        json.dumps(
            {
                "scenario": "simple_route",
                "status": "PASS",
                "duration_sec": duration_sec,
                "metrics": {
                    "path_length_m": path_length_m,
                    "distance_to_goal_m": 0.25,
                    "stuck_events": 0,
                    "feedback_samples": 20,
                    "recoveries": 0,
                },
            }
        ),
        encoding="utf-8",
    )


def test_compare_json_prints_stable_machine_readable_report(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    candidate = tmp_path / "candidate.json"
    _write_result(baseline)
    _write_result(candidate, duration_sec=10.5, path_length_m=5.2)

    result = runner.invoke(
        app,
        [
            "compare",
            "--baseline",
            str(baseline),
            "--candidate",
            str(candidate),
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["schema_version"] == 1
    assert payload["status"] == "PASS"
    assert payload["baseline"] == str(baseline)
    assert payload["candidate"] == str(candidate)
    assert payload["findings"] == []
    assert payload["policy"]["max_duration_increase_pct"] == 10.0


def test_compare_output_writes_report_before_regression_exit(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    candidate = tmp_path / "candidate.json"
    report_path = tmp_path / "artifacts" / "regression.json"
    _write_result(baseline)
    _write_result(candidate, duration_sec=12.0, path_length_m=6.0)

    result = runner.invoke(
        app,
        [
            "compare",
            "--baseline",
            str(baseline),
            "--candidate",
            str(candidate),
            "--output",
            str(report_path),
        ],
    )

    assert result.exit_code == 4
    assert report_path.exists()
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["status"] == "REGRESSION"
    assert {finding["metric"] for finding in payload["findings"]} == {
        "duration_sec",
        "path_length_m",
    }
    assert f"Report: {report_path}" in result.stdout


def test_compare_json_uses_null_for_unbounded_percentage(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    candidate = tmp_path / "candidate.json"
    _write_result(baseline, duration_sec=0.0)
    _write_result(candidate, duration_sec=1.0)

    result = runner.invoke(
        app,
        [
            "compare",
            "--baseline",
            str(baseline),
            "--candidate",
            str(candidate),
            "--json",
        ],
    )

    assert result.exit_code == 4
    assert "Infinity" not in result.stdout
    payload = json.loads(result.stdout)
    duration = next(
        finding for finding in payload["findings"] if finding["metric"] == "duration_sec"
    )
    assert duration["increase"] is None
    assert duration["increase_unbounded"] is True
