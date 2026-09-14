from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from dataclasses import asdict
from pathlib import Path

from typer.testing import CliRunner

from robotci.reproducibility import (
    RuntimePackage,
    build_runtime_environment,
    build_suite_execution_identity,
)
from robotci.results import Pose2D, build_scenario_task
from robotci.suite_cli import app

runner = CliRunner()

_TEST_ENVIRONMENT = build_runtime_environment(
    os_id="ubuntu",
    os_version="24.04",
    architecture="x86_64",
    python_version="3.12.3",
    ros_distro="jazzy",
    containerized=False,
    packages=(RuntimePackage(manager="python", name="robotci", version="0.0.1"),),
)
_TEST_EXECUTION = build_suite_execution_identity(
    runtime="native",
    plan_fingerprint="sha256:" + "1" * 64,
    environment=_TEST_ENVIRONMENT,
)


def _write_result(
    path: Path,
    *,
    scenario: str,
    duration_sec: float,
    path_length_m: float,
    distance_to_goal_m: float = 0.1,
) -> None:
    start = Pose2D(x=0.0, y=0.0, yaw=0.0)
    goal = Pose2D(x=1.0, y=0.0, yaw=0.0)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "scenario": scenario,
                "status": "PASS",
                "duration_sec": duration_sec,
                "navigation_result": "SUCCEEDED",
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
                    "distance_to_goal_m": distance_to_goal_m,
                    "stuck_events": 0,
                    "feedback_samples": 10,
                    "recoveries": 0,
                },
                "telemetry_quality": {
                    "received_feedback_samples": 10,
                    "valid_pose_samples": 10,
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


def _write_suite(
    root: Path,
    *,
    duration: float,
    path_length: float,
    distance_to_goal_m: float = 0.1,
) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    result = root / "results" / "route.json"
    _write_result(
        result,
        scenario="route",
        duration_sec=duration,
        path_length_m=path_length,
        distance_to_goal_m=distance_to_goal_m,
    )
    suite = root / "suite-result.json"
    suite.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "status": "PASS",
                "runtime": "native",
                "execution": asdict(_TEST_EXECUTION),
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
    assert payload["schema_version"] == 2
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


def test_suite_gate_writes_junit_before_regression_exit(tmp_path: Path) -> None:
    baseline = _write_suite(tmp_path / "baseline", duration=10.0, path_length=5.0)
    candidate = _write_suite(tmp_path / "candidate", duration=12.0, path_length=6.0)
    junit = tmp_path / "artifacts" / "suite-regression.xml"

    result = runner.invoke(
        app,
        [
            "--baseline",
            str(baseline),
            "--candidate",
            str(candidate),
            "--junit-output",
            str(junit),
        ],
    )

    assert result.exit_code == 4
    root = ET.parse(junit).getroot()
    assert root.tag == "testsuite"
    assert root.attrib["tests"] == "1"
    assert root.attrib["failures"] == "1"
    case = root.find("testcase")
    assert case is not None
    assert case.attrib["name"] == "route"
    failure = case.find("failure")
    assert failure is not None
    assert failure.attrib["type"] == "REGRESSION"
    assert "duration" in (failure.text or "")
    assert "path_length" in (failure.text or "")


def test_suite_gate_honors_distance_threshold_override(tmp_path: Path) -> None:
    baseline = _write_suite(
        tmp_path / "baseline",
        duration=10.0,
        path_length=5.0,
        distance_to_goal_m=0.05,
    )
    candidate = _write_suite(
        tmp_path / "candidate",
        duration=10.0,
        path_length=5.0,
        distance_to_goal_m=0.2,
    )

    blocked = runner.invoke(
        app,
        [
            "--baseline",
            str(baseline),
            "--candidate",
            str(candidate),
            "--json",
        ],
    )
    allowed = runner.invoke(
        app,
        [
            "--baseline",
            str(baseline),
            "--candidate",
            str(candidate),
            "--max-distance-to-goal-increase-m",
            "0.2",
        ],
    )

    assert blocked.exit_code == 4
    blocked_payload = json.loads(blocked.stdout)
    assert [
        finding["metric"]
        for finding in blocked_payload["scenarios"][0]["findings"]
    ] == ["distance_to_goal_m"]
    assert allowed.exit_code == 0


def test_suite_gate_writes_passing_junit(tmp_path: Path) -> None:
    baseline = _write_suite(tmp_path / "baseline", duration=10.0, path_length=5.0)
    candidate = _write_suite(tmp_path / "candidate", duration=10.5, path_length=5.1)
    junit = tmp_path / "artifacts" / "suite-pass.xml"

    result = runner.invoke(
        app,
        [
            "--baseline",
            str(baseline),
            "--candidate",
            str(candidate),
            "--junit-output",
            str(junit),
        ],
    )

    assert result.exit_code == 0
    root = ET.parse(junit).getroot()
    assert root.attrib["tests"] == "1"
    assert root.attrib["failures"] == "0"
    case = root.find("testcase")
    assert case is not None
    assert case.find("failure") is None
