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
    scenario: str = "simple_route",
    status: str = "PASS",
    duration_sec: float = 10.0,
    path_length_m: float = 5.0,
    stuck_events: int = 0,
    recoveries: int = 0,
) -> None:
    start = Pose2D(x=0.0, y=0.0, yaw=0.0)
    goal = Pose2D(x=1.0, y=0.0, yaw=0.0)
    path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "scenario": scenario,
                "status": status,
                "duration_sec": duration_sec,
                "navigation_result": "SUCCEEDED" if status == "PASS" else status,
                "start": asdict(start),
                "goal": asdict(goal),
                "task": asdict(
                    build_scenario_task(
                        scenario=scenario,
                        start=start,
                        goal=goal,
                        map_id="nav2-loopback",
                    )
                ),
                "metrics": {
                    "path_length_m": path_length_m,
                    "distance_to_goal_m": 0.25,
                    "stuck_events": stuck_events,
                    "feedback_samples": 20,
                    "recoveries": recoveries,
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
                **({"reason_code": status.lower()} if status != "PASS" else {}),
            }
        ),
        encoding="utf-8",
    )


def test_compare_command_passes_within_default_policy(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    candidate = tmp_path / "candidate.json"
    _write_result(baseline)
    _write_result(candidate, duration_sec=10.5, path_length_m=5.2)

    result = runner.invoke(
        app,
        ["compare", "--baseline", str(baseline), "--candidate", str(candidate)],
    )

    assert result.exit_code == 0
    assert "Regression verdict" in result.stdout
    assert "PASS" in result.stdout


def test_compare_command_exits_four_for_regression(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    candidate = tmp_path / "candidate.json"
    _write_result(baseline)
    _write_result(candidate, duration_sec=12.0, path_length_m=6.0)

    result = runner.invoke(
        app,
        ["compare", "--baseline", str(baseline), "--candidate", str(candidate)],
    )

    assert result.exit_code == 4
    assert "REGRESSION" in result.stdout
    assert "duration_sec" in result.stdout
    assert "path_length_m" in result.stdout


def test_compare_command_accepts_custom_thresholds(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    candidate = tmp_path / "candidate.json"
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
            "--max-duration-increase-pct",
            "25",
            "--max-path-length-increase-pct",
            "25",
        ],
    )

    assert result.exit_code == 0
    assert "PASS" in result.stdout


def test_compare_command_reports_invalid_input(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.json"
    candidate = tmp_path / "candidate.json"
    _write_result(baseline)
    _write_result(candidate, status="TIMEOUT")

    result = runner.invoke(
        app,
        ["compare", "--baseline", str(baseline), "--candidate", str(candidate)],
    )

    assert result.exit_code == 3
    assert "RobotCI comparison error" in result.stdout
    assert "must have PASS status" in result.stdout
