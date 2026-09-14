from __future__ import annotations

from pathlib import Path

from robotci.regression import RegressionPolicy, RegressionReport, compare_navigation_metrics
from robotci.result_schema import (
    ResultSchemaError,
    ValidatedScenarioResult,
    load_result,
    validate_result_payload,
)
from robotci.results import RESULT_SCHEMA_VERSION


class ComparisonInputError(ValueError):
    """Raised when a persisted result cannot be used for regression comparison."""


ScenarioSnapshot = ValidatedScenarioResult


def _require_comparable(result: ValidatedScenarioResult) -> ScenarioSnapshot:
    if result.source_schema_version != RESULT_SCHEMA_VERSION:
        raise ComparisonInputError(
            "legacy result schema v0 has incomplete task provenance; "
            "rerun the scenario to create a current result before comparison"
        )
    if result.status != "PASS":
        raise ComparisonInputError(
            f"scenario '{result.scenario}' must have PASS status before metrics "
            "can be compared"
        )
    if result.task is None or not result.provenance_complete:
        raise ComparisonInputError(
            "task.map_id must identify the map before regression comparison"
        )
    if result.metrics is None:
        raise ComparisonInputError("PASS result must include navigation metrics")
    return result


def parse_scenario_result(payload: object) -> ScenarioSnapshot:
    """Validate a result and require complete provenance for comparison."""

    try:
        result = validate_result_payload(payload)
    except ResultSchemaError as exc:
        raise ComparisonInputError(str(exc)) from exc
    return _require_comparable(result)


def load_scenario_result(path: str | Path) -> ScenarioSnapshot:
    try:
        result = load_result(path)
    except ResultSchemaError as exc:
        raise ComparisonInputError(str(exc)) from exc
    return _require_comparable(result)


def compare_scenario_results(
    *,
    baseline: ScenarioSnapshot,
    candidate: ScenarioSnapshot,
    policy: RegressionPolicy | None = None,
) -> RegressionReport:
    if baseline.scenario != candidate.scenario:
        raise ComparisonInputError(
            "baseline and candidate must describe the same scenario "
            f"('{baseline.scenario}' != '{candidate.scenario}')"
        )

    if (
        baseline.task is None
        or candidate.task is None
        or baseline.task.fingerprint != candidate.task.fingerprint
    ):
        raise ComparisonInputError(
            "baseline and candidate describe different tasks; "
            "scenario start, goal, frame and map must match"
        )
    if baseline.metrics is None or candidate.metrics is None:
        raise ComparisonInputError("both results must include navigation metrics")

    return compare_navigation_metrics(
        baseline_duration_sec=baseline.duration_sec,
        baseline=baseline.metrics,
        candidate_duration_sec=candidate.duration_sec,
        candidate=candidate.metrics,
        policy=policy,
    )


def compare_scenario_result_files(
    *,
    baseline_path: str | Path,
    candidate_path: str | Path,
    policy: RegressionPolicy | None = None,
) -> RegressionReport:
    return compare_scenario_results(
        baseline=load_scenario_result(baseline_path),
        candidate=load_scenario_result(candidate_path),
        policy=policy,
    )
