from __future__ import annotations

import json

from robotci.results import (
    Pose2D,
    ScenarioResult,
    SuiteResult,
    SuiteScenarioResult,
    write_result,
    write_suite_result,
)


def test_write_result_creates_portable_json(tmp_path) -> None:
    result = ScenarioResult(
        scenario="simple_route",
        status="PASS",
        duration_sec=12.345,
        start=Pose2D(x=0.0, y=0.0, yaw=0.0),
        goal=Pose2D(x=17.86, y=-0.77, yaw=0.0),
        navigation_result="SUCCEEDED",
    )

    output = tmp_path / "nested" / "result.json"
    written = write_result(result, output)

    assert written == output
    assert written.exists()

    payload = json.loads(written.read_text(encoding="utf-8"))
    assert payload == {
        "duration_sec": 12.345,
        "goal": {"x": 17.86, "y": -0.77, "yaw": 0.0},
        "navigation_result": "SUCCEEDED",
        "scenario": "simple_route",
        "start": {"x": 0.0, "y": 0.0, "yaw": 0.0},
        "status": "PASS",
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
    )

    output = tmp_path / "suite-result.json"
    written = write_suite_result(suite, output)
    payload = json.loads(written.read_text(encoding="utf-8"))

    assert payload["status"] == "PASS"
    assert payload["runtime"] == "native"
    assert payload["scenarios"][0]["scenario"] == "short_route"
    assert payload["scenarios"][0]["result_file"] == "results/short_route.json"
