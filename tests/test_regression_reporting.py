from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from typer.testing import CliRunner

from robotci.cli import app
from robotci.results import Pose2D, build_scenario_task

runner = CliRunner()


def _write_result(
    path: Path,
    *,
    duration_sec: float = 10.0,
    path_length_m: float = 5.0,
    distance_to_goal_m: float = 0.1,
) -> None:
    start = Pose2D(x=0.0, y=0.0, yaw=0.0)
    goal = Pose2D(x=1.0, y=0.0, yaw=0.0)
    path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "scenario": "simple_route",
                "status": "PASS",
                "duration_sec": duration_sec,
                "navigation_result": "SUCCEEDED",
                "start": asdict(start),
                "goal": asdict(goal),
                "task": asdict(
                    build_scenario_task(
                        scenario="simple_route",
                        start=start,
                        goal=goal,
                        map_id="nav2-loopback",
                    )
                ),
                "metrics": {
                    "path_length_m": path_length_m,
                    "distance_to_goal_m": distance_to_goal_m,
                    "stuck_events": 0,
                    "feedback_samples": 20,
                    "recoveries": 0,
                },
                "telemetry_quality": {
                    "received_feedback_samples": 20,
                    "valid_pose_samples": 20,
                    "invalid_pose_samples": 0,
                    "final_pose_valid": True,
                },
                "evidence_policy": {
                    "goal_tolerance_m": 0.25,
                    "min_feedback_samples": 1,
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
    assert payload["schema_version"] == 2
    assert payload["status"] == "PASS"
    assert payload["baseline"] == str(baseline)
    assert payload["candidate"] == str(candidate)
    assert payload["findings"] == []
    assert payload["policy"]["max_duration_increase_pct"] == 10.0
    assert payload["policy"]["max_distance_to_goal_increase_m"] == 0.1


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
