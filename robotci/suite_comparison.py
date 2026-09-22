from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from robotci.comparison import (
    ComparisonInputError,
    compare_scenario_results,
    require_comparable_result,
)
from robotci.regression import RegressionPolicy, RegressionReport
from robotci.reproducibility import SuiteExecutionIdentity
from robotci.suite_schema import (
    SuiteResultError,
    ValidatedSuiteResult,
    load_suite_result,
)


@dataclass(frozen=True)
class SuiteScenarioComparison:
    scenario: str
    baseline_result: Path
    candidate_result: Path
    report: RegressionReport


@dataclass(frozen=True)
class SuiteRegressionReport:
    status: Literal["PASS", "REGRESSION"]
    scenarios: tuple[SuiteScenarioComparison, ...]


def _load_suite(path: str | Path, name: str) -> ValidatedSuiteResult:
    try:
        suite = load_suite_result(path)
    except SuiteResultError as exc:
        raise ComparisonInputError(f"{name}: {exc}") from exc
    if suite.status != "PASS":
        raise ComparisonInputError(f"{name} must have PASS status before regression comparison")
    for entry in suite.scenarios:
        if entry.status != "PASS":
            raise ComparisonInputError(
                f"{name} scenario '{entry.scenario}' must have PASS status before comparison"
            )
    return suite


def _execution_mismatch(
    baseline: SuiteExecutionIdentity,
    candidate: SuiteExecutionIdentity,
) -> str:
    details: list[str] = []
    if baseline.runtime != candidate.runtime:
        details.append(f"runtime differs: {baseline.runtime} != {candidate.runtime}")
    if baseline.runtime_contract != candidate.runtime_contract:
        details.append("runtime contract differs")
    if baseline.plan_fingerprint != candidate.plan_fingerprint:
        details.append("effective suite plan differs")
    if baseline.environment.fingerprint != candidate.environment.fingerprint:
        details.append("runtime environment differs")
    return "; ".join(details) or "execution fingerprint differs"


def compare_suite_result_files(
    *,
    baseline_path: str | Path,
    candidate_path: str | Path,
    policy: RegressionPolicy | None = None,
) -> SuiteRegressionReport:
    """Compare every matching scenario in two successful suite result files."""
    selected_policy = policy or RegressionPolicy()
    baseline_suite = _load_suite(baseline_path, "baseline suite")
    candidate_suite = _load_suite(candidate_path, "candidate suite")
    baseline_entries = baseline_suite.scenarios
    candidate_entries = candidate_suite.scenarios
    baseline_execution = baseline_suite.execution
    candidate_execution = candidate_suite.execution
    if baseline_execution.fingerprint != candidate_execution.fingerprint:
        raise ComparisonInputError(
            "suite execution fingerprints must match ("
            + _execution_mismatch(baseline_execution, candidate_execution)
            + ")"
        )
    candidate_by_name = {entry.scenario: entry for entry in candidate_entries}

    baseline_names = {entry.scenario for entry in baseline_entries}
    candidate_names = set(candidate_by_name)
    if baseline_names != candidate_names:
        missing = sorted(baseline_names - candidate_names)
        extra = sorted(candidate_names - baseline_names)
        details: list[str] = []
        if missing:
            details.append(f"missing from candidate: {', '.join(missing)}")
        if extra:
            details.append(f"only in candidate: {', '.join(extra)}")
        raise ComparisonInputError("suite scenarios must match (" + "; ".join(details) + ")")

    comparisons: list[SuiteScenarioComparison] = []
    for baseline_entry in baseline_entries:
        candidate_entry = candidate_by_name[baseline_entry.scenario]
        baseline_snapshot = require_comparable_result(baseline_entry.result)
        candidate_snapshot = require_comparable_result(candidate_entry.result)

        scenario_report = compare_scenario_results(
            baseline=baseline_snapshot,
            candidate=candidate_snapshot,
            policy=selected_policy,
        )
        comparisons.append(
            SuiteScenarioComparison(
                scenario=baseline_entry.scenario,
                baseline_result=baseline_entry.result_path,
                candidate_result=candidate_entry.result_path,
                report=scenario_report,
            )
        )

    status: Literal["PASS", "REGRESSION"] = (
        "REGRESSION"
        if any(item.report.status == "REGRESSION" for item in comparisons)
        else "PASS"
    )
    return SuiteRegressionReport(status=status, scenarios=tuple(comparisons))
