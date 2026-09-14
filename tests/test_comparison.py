from __future__ import annotations

import json
from dataclasses import asdict

import pytest

from robotci.comparison import (
    ComparisonInputError,
    compare_scenario_result_files,
    compare_scenario_results,
    load_scenario_result,
    parse_scenario_result,
)
from robotci.results import Pose2D, build_scenario_task


def _payload(
    *,
    scenario: str = "simple_route",
    status: str = "PASS",
    duration_sec: float = 10.0,
    path_length_m: float = 5.0,
    stuck_events: int = 0,
    feedback_samples: int = 20,
    recoveries: int = 0,
    goal_x: float = 1.0,
    map_id: str = "nav2-loopback",
) -> dict[str, object]:
    start = Pose2D(x=0.0, y=0.0, yaw=0.0)
    goal = Pose2D(x=goal_x, y=2.0, yaw=0.0)
    return {
        "schema_version": 1,
        "scenario": scenario,
        "status": status,
        "duration_sec": duration_sec,
        "start": asdict(start),
        "goal": asdict(goal),
        "task": asdict(
            build_scenario_task(
                scenario=scenario,
                start=start,
                goal=goal,
                map_id=map_id,
            )
        ),
        "metrics": {
            "path_length_m": path_length_m,
            "distance_to_goal_m": 0.25,
            "stuck_events": stuck_events,
            "feedback_samples": feedback_samples,
            "recoveries": recoveries,
        },
    }


def test_parse_scenario_result_reads_comparison_fields() -> None:
    snapshot = parse_scenario_result(_payload())

    assert snapshot.scenario == "simple_route"
    assert snapshot.duration_sec == 10.0
    assert snapshot.metrics.path_length_m == 5.0
    assert snapshot.metrics.feedback_samples == 20
    assert snapshot.task.map_id == "nav2-loopback"


def test_parse_scenario_result_requires_pass_status() -> None:
    with pytest.raises(ComparisonInputError, match="must have PASS status"):
        parse_scenario_result(_payload(status="TIMEOUT"))


def test_parse_scenario_result_rejects_invalid_metric_types() -> None:
    payload = _payload()
    metrics = payload["metrics"]
    assert isinstance(metrics, dict)
    metrics["stuck_events"] = True

    with pytest.raises(ComparisonInputError, match="metrics.stuck_events"):
        parse_scenario_result(payload)


def test_load_scenario_result_reports_invalid_json(tmp_path) -> None:
    result_path = tmp_path / "result.json"
    result_path.write_text("not-json", encoding="utf-8")

    with pytest.raises(ComparisonInputError, match="invalid JSON"):
        load_scenario_result(result_path)


def test_compare_scenario_results_requires_matching_scenarios() -> None:
    baseline = parse_scenario_result(_payload(scenario="short_route"))
    candidate = parse_scenario_result(_payload(scenario="simple_route"))

    with pytest.raises(ComparisonInputError, match="same scenario"):
        compare_scenario_results(baseline=baseline, candidate=candidate)


def test_compare_rejects_changed_goal_even_when_metrics_match() -> None:
    baseline = parse_scenario_result(_payload())
    candidate = parse_scenario_result(_payload(goal_x=10.0))

    with pytest.raises(ComparisonInputError, match="different tasks"):
        compare_scenario_results(baseline=baseline, candidate=candidate)


def test_compare_rejects_changed_map_even_when_metrics_match() -> None:
    baseline = parse_scenario_result(_payload(map_id="warehouse-v1"))
    candidate = parse_scenario_result(_payload(map_id="warehouse-v2"))

    with pytest.raises(ComparisonInputError, match="different tasks"):
        compare_scenario_results(baseline=baseline, candidate=candidate)


def test_parse_rejects_tampered_task_fingerprint() -> None:
    payload = _payload()
    task = payload["task"]
    assert isinstance(task, dict)
    task["fingerprint"] = "sha256:" + "0" * 64

    with pytest.raises(ComparisonInputError, match="fingerprint does not match"):
        parse_scenario_result(payload)


def test_parse_requires_map_identity_for_comparison() -> None:
    with pytest.raises(ComparisonInputError, match="must identify the map"):
        parse_scenario_result(_payload(map_id="unspecified"))


def test_compare_allows_controller_metadata_to_change() -> None:
    baseline_payload = _payload()
    candidate_payload = _payload()
    baseline_payload["controller_id"] = "regulated-pure-pursuit"
    candidate_payload["controller_id"] = "mppi"

    report = compare_scenario_results(
        baseline=parse_scenario_result(baseline_payload),
        candidate=parse_scenario_result(candidate_payload),
    )

    assert report.status == "PASS"


def test_compare_scenario_result_files_detects_regression(tmp_path) -> None:
    baseline_path = tmp_path / "baseline.json"
    candidate_path = tmp_path / "candidate.json"
    baseline_path.write_text(json.dumps(_payload()), encoding="utf-8")
    candidate_path.write_text(
        json.dumps(_payload(duration_sec=12.0, path_length_m=6.0)),
        encoding="utf-8",
    )

    report = compare_scenario_result_files(
        baseline_path=baseline_path,
        candidate_path=candidate_path,
    )

    assert report.status == "REGRESSION"
    assert [finding.metric for finding in report.findings] == [
        "duration_sec",
        "path_length_m",
    ]
