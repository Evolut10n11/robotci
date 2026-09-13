from __future__ import annotations

import json
from pathlib import Path

import pytest

from robotci.comparison import ComparisonInputError
from robotci.suite_comparison import compare_suite_result_files


def _write_result(
    path: Path,
    *,
    scenario: str,
    duration_sec: float = 10.0,
    path_length_m: float = 5.0,
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


def _write_suite(path: Path, scenarios: list[str]) -> None:
    path.write_text(
        json.dumps(
            {
                "status": "PASS",
                "runtime": "native",
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
