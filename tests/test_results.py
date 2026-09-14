from __future__ import annotations

import json
import math
from dataclasses import asdict

import pytest

from robotci.evidence import NavigationEvidencePolicy
from robotci.metrics import NavigationMetrics, NavigationTelemetryQuality
from robotci.reproducibility import (
    RuntimePackage,
    build_runtime_environment,
    build_suite_execution_identity,
)
from robotci.result_schema import ResultSchemaError
from robotci.results import (
    Pose2D,
    ScenarioResult,
    SuiteResult,
    SuiteScenarioResult,
    build_scenario_task,
    write_result,
    write_suite_result,
)


def test_write_result_creates_portable_json(tmp_path) -> None:
    start = Pose2D(x=0.0, y=0.0, yaw=0.0)
    goal = Pose2D(x=17.86, y=-0.77, yaw=0.0)
    task = build_scenario_task(
        scenario="simple_route",
        start=start,
        goal=goal,
        map_id="nav2-loopback",
    )
    result = ScenarioResult(
        scenario="simple_route",
        status="PASS",
        duration_sec=12.345,
        start=start,
        goal=goal,
        navigation_result="SUCCEEDED",
        metrics=NavigationMetrics(
            path_length_m=18.024,
            distance_to_goal_m=0.011,
            stuck_events=0,
            feedback_samples=95,
            recoveries=0,
        ),
        telemetry_quality=NavigationTelemetryQuality(
            received_feedback_samples=95,
            valid_pose_samples=95,
            invalid_pose_samples=0,
            final_pose_valid=True,
        ),
        evidence_policy=NavigationEvidencePolicy(goal_tolerance_m=0.25),
        task=task,
    )

    output = tmp_path / "nested" / "result.json"
    written = write_result(result, output)

    assert written == output
    assert written.exists()

    payload = json.loads(written.read_text(encoding="utf-8"))
    assert payload == {
        "duration_sec": 12.345,
        "goal": {"x": 17.86, "y": -0.77, "yaw": 0.0},
        "metrics": {
            "distance_to_goal_m": 0.011,
            "feedback_samples": 95,
            "path_length_m": 18.024,
            "recoveries": 0,
            "stuck_events": 0,
        },
        "navigation_result": "SUCCEEDED",
        "scenario": "simple_route",
        "schema_version": 2,
        "start": {"x": 0.0, "y": 0.0, "yaw": 0.0},
        "status": "PASS",
        "telemetry_quality": {
            "final_pose_valid": True,
            "invalid_pose_samples": 0,
            "received_feedback_samples": 95,
            "valid_pose_samples": 95,
        },
        "evidence_policy": {
            "goal_tolerance_m": 0.25,
            "min_feedback_samples": 1,
        },
        "task": asdict(task),
    }


def test_write_suite_result_serializes_scenario_summaries(tmp_path) -> None:
    suite = SuiteResult(
        status="PASS",
        runtime="native",
        duration_sec=15.0,
        scenarios=(
            SuiteScenarioResult(
                scenario="short_route",
                status="PASS",
                duration_sec=4.0,
                result_file="results/short_route.json",
            ),
        ),
        execution=build_suite_execution_identity(
            runtime="native",
            plan_fingerprint="sha256:" + "1" * 64,
            environment=build_runtime_environment(
                os_id="ubuntu",
                os_version="24.04",
                architecture="x86_64",
                python_version="3.12.3",
                ros_distro="jazzy",
                containerized=False,
                packages=(
                    RuntimePackage(
                        manager="python",
                        name="robotci",
                        version="0.0.1",
                    ),
                ),
            ),
        ),
    )

    output = tmp_path / "suite-result.json"
    written = write_suite_result(suite, output)
    payload = json.loads(written.read_text(encoding="utf-8"))

    assert payload["schema_version"] == 1
    assert payload["status"] == "PASS"
    assert payload["runtime"] == "native"
    assert payload["execution"]["fingerprint"].startswith("sha256:")
    assert payload["execution"]["environment"]["os_id"] == "ubuntu"
    assert payload["scenarios"][0]["scenario"] == "short_route"
    assert payload["scenarios"][0]["result_file"] == "results/short_route.json"


def test_task_fingerprint_normalizes_equivalent_numeric_values() -> None:
    integer_task = build_scenario_task(
        scenario="route",
        start=Pose2D(x=0, y=-0.0, yaw=0),
        goal=Pose2D(x=1, y=2, yaw=0),
        map_id="warehouse-v1",
    )
    float_task = build_scenario_task(
        scenario="route",
        start=Pose2D(x=0.0, y=0.0, yaw=0.0),
        goal=Pose2D(x=1.0, y=2.0, yaw=0.0),
        map_id="warehouse-v1",
    )

    assert integer_task.fingerprint == float_task.fingerprint


def test_task_fingerprint_rejects_non_finite_pose() -> None:
    with pytest.raises(ValueError, match="finite numbers"):
        build_scenario_task(
            scenario="route",
            start=Pose2D(x=math.nan, y=0.0, yaw=0.0),
            goal=Pose2D(x=1.0, y=2.0, yaw=0.0),
            map_id="warehouse-v1",
        )


def test_write_result_rejects_non_finite_metrics(tmp_path) -> None:
    start = Pose2D(x=0.0, y=0.0, yaw=0.0)
    goal = Pose2D(x=1.0, y=0.0, yaw=0.0)
    result = ScenarioResult(
        scenario="route",
        status="PASS",
        duration_sec=1.0,
        start=start,
        goal=goal,
        navigation_result="SUCCEEDED",
        metrics=NavigationMetrics(
            path_length_m=math.nan,
            distance_to_goal_m=0.0,
            stuck_events=0,
            feedback_samples=1,
            recoveries=0,
        ),
        telemetry_quality=NavigationTelemetryQuality(
            received_feedback_samples=1,
            valid_pose_samples=1,
            invalid_pose_samples=0,
            final_pose_valid=True,
        ),
        evidence_policy=NavigationEvidencePolicy(),
        task=build_scenario_task(
            scenario="route",
            start=start,
            goal=goal,
            map_id="warehouse-v1",
        ),
    )

    with pytest.raises(ResultSchemaError, match="path_length_m must be finite"):
        write_result(result, tmp_path / "result.json")
