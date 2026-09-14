from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import pytest

from robotci.comparison import ComparisonInputError
from robotci.reproducibility import (
    RuntimePackage,
    build_runtime_environment,
    build_suite_execution_identity,
)
from robotci.results import Pose2D, build_scenario_task
from robotci.suite_comparison import compare_suite_result_files


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
    duration_sec: float = 10.0,
    path_length_m: float = 5.0,
    distance_to_goal_m: float = 0.1,
    goal_x: float = 1.0,
    map_id: str = "nav2-loopback",
) -> None:
    start = Pose2D(x=0.0, y=0.0, yaw=0.0)
    goal = Pose2D(x=goal_x, y=0.0, yaw=0.0)
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
                        map_id=map_id,
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


def _write_suite(path: Path, scenarios: list[str]) -> None:
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "status": "PASS",
                "runtime": "native",
                "execution": asdict(_TEST_EXECUTION),
                "duration_sec": 20.0,
                "scenarios": [
                    {
                        "scenario": scenario,
                        "status": "PASS",
                        "duration_sec": 10.0,
                        "result_file": f"results/{scenario}.json",
                    }
                    for scenario in scenarios
                ],
            }
        ),
        encoding="utf-8",
    )


def _make_suite(root: Path, values: dict[str, tuple[float, float]]) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    suite = root / "suite-result.json"
    _write_suite(suite, list(values))
    for scenario, (duration, path_length) in values.items():
        _write_result(
            root / "results" / f"{scenario}.json",
            scenario=scenario,
            duration_sec=duration,
            path_length_m=path_length,
        )
    return suite


def test_suite_comparison_passes_when_all_scenarios_are_within_policy(tmp_path: Path) -> None:
    baseline = _make_suite(tmp_path / "baseline", {"a": (10.0, 5.0), "b": (20.0, 8.0)})
    candidate = _make_suite(tmp_path / "candidate", {"a": (10.5, 5.2), "b": (21.0, 8.4)})

    report = compare_suite_result_files(baseline_path=baseline, candidate_path=candidate)

    assert report.status == "PASS"
    assert [item.scenario for item in report.scenarios] == ["a", "b"]


def test_suite_comparison_regresses_when_any_scenario_regresses(tmp_path: Path) -> None:
    baseline = _make_suite(tmp_path / "baseline", {"a": (10.0, 5.0), "b": (20.0, 8.0)})
    candidate = _make_suite(tmp_path / "candidate", {"a": (10.0, 5.0), "b": (25.0, 10.0)})

    report = compare_suite_result_files(baseline_path=baseline, candidate_path=candidate)

    assert report.status == "REGRESSION"
    assert report.scenarios[0].report.status == "PASS"
    assert report.scenarios[1].report.status == "REGRESSION"


def test_suite_comparison_flags_distance_degradation(tmp_path: Path) -> None:
    baseline = _make_suite(tmp_path / "baseline", {"a": (10.0, 5.0)})
    candidate = _make_suite(tmp_path / "candidate", {"a": (10.0, 5.0)})
    _write_result(
        candidate.parent / "results" / "a.json",
        scenario="a",
        distance_to_goal_m=0.21,
    )

    report = compare_suite_result_files(
        baseline_path=baseline,
        candidate_path=candidate,
    )

    assert report.status == "REGRESSION"
    assert [finding.metric for finding in report.scenarios[0].report.findings] == [
        "distance_to_goal_m"
    ]


def test_suite_comparison_rejects_result_path_traversal(tmp_path: Path) -> None:
    baseline = _make_suite(tmp_path / "baseline", {"a": (10.0, 5.0)})
    candidate = _make_suite(tmp_path / "candidate", {"a": (10.0, 5.0)})
    outside_result = tmp_path / "outside.json"
    _write_result(outside_result, scenario="a")

    payload = json.loads(candidate.read_text(encoding="utf-8"))
    payload["scenarios"][0]["result_file"] = "../outside.json"
    candidate.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ComparisonInputError, match="unsafe result_file path"):
        compare_suite_result_files(
            baseline_path=baseline,
            candidate_path=candidate,
        )


def test_suite_comparison_requires_matching_scenario_sets(tmp_path: Path) -> None:
    baseline = _make_suite(tmp_path / "baseline", {"a": (10.0, 5.0), "b": (20.0, 8.0)})
    candidate = _make_suite(tmp_path / "candidate", {"a": (10.0, 5.0)})

    with pytest.raises(ComparisonInputError, match="missing from candidate: b"):
        compare_suite_result_files(baseline_path=baseline, candidate_path=candidate)


def test_suite_entry_must_point_to_its_declared_scenario(tmp_path: Path) -> None:
    baseline = _make_suite(tmp_path / "baseline", {"a": (10.0, 5.0)})
    candidate = _make_suite(tmp_path / "candidate", {"a": (10.0, 5.0)})
    _write_result(
        baseline.parent / "results" / "a.json",
        scenario="wrong_name",
    )

    with pytest.raises(ComparisonInputError, match="points to result for 'wrong_name'"):
        compare_suite_result_files(baseline_path=baseline, candidate_path=candidate)


def test_suite_comparison_rejects_changed_task_definition(tmp_path: Path) -> None:
    baseline = _make_suite(tmp_path / "baseline", {"a": (10.0, 5.0)})
    candidate = _make_suite(tmp_path / "candidate", {"a": (10.0, 5.0)})
    _write_result(
        candidate.parent / "results" / "a.json",
        scenario="a",
        goal_x=2.0,
    )

    with pytest.raises(ComparisonInputError, match="different tasks"):
        compare_suite_result_files(baseline_path=baseline, candidate_path=candidate)


def test_suite_comparison_rejects_different_runtime_environment(tmp_path: Path) -> None:
    baseline = _make_suite(tmp_path / "baseline", {"a": (10.0, 5.0)})
    candidate = _make_suite(tmp_path / "candidate", {"a": (10.0, 5.0)})
    changed_environment = build_runtime_environment(
        os_id="ubuntu",
        os_version="24.04",
        architecture="x86_64",
        python_version="3.12.4",
        ros_distro="jazzy",
        containerized=False,
        packages=(RuntimePackage(manager="python", name="robotci", version="0.0.1"),),
    )
    changed_execution = build_suite_execution_identity(
        runtime="native",
        plan_fingerprint=_TEST_EXECUTION.plan_fingerprint,
        environment=changed_environment,
    )
    payload = json.loads(candidate.read_text(encoding="utf-8"))
    payload["execution"] = asdict(changed_execution)
    candidate.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ComparisonInputError, match="runtime environment differs"):
        compare_suite_result_files(baseline_path=baseline, candidate_path=candidate)


def test_suite_comparison_rejects_legacy_suite_without_execution(tmp_path: Path) -> None:
    baseline = _make_suite(tmp_path / "baseline", {"a": (10.0, 5.0)})
    candidate = _make_suite(tmp_path / "candidate", {"a": (10.0, 5.0)})
    payload = json.loads(candidate.read_text(encoding="utf-8"))
    payload.pop("schema_version")
    payload.pop("execution")
    candidate.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ComparisonInputError, match="schema_version must be 1"):
        compare_suite_result_files(baseline_path=baseline, candidate_path=candidate)
