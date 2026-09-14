from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from robotci.comparison import (
    ComparisonInputError,
    compare_scenario_results,
    load_scenario_result,
)
from robotci.regression import RegressionPolicy, RegressionReport
from robotci.reproducibility import (
    ReproducibilityError,
    SuiteExecutionIdentity,
    validate_suite_execution,
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


@dataclass(frozen=True)
class _SuiteEntry:
    scenario: str
    result_path: Path


def _load_json_object(path: Path, name: str) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ComparisonInputError(f"cannot read {name} '{path}': {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ComparisonInputError(f"invalid JSON in {name} '{path}': {exc}") from exc
    if not isinstance(payload, dict):
        raise ComparisonInputError(f"{name} must contain a JSON object")
    return payload


def _safe_result_path(
    *,
    suite_path: Path,
    result_file: str,
    suite_name: str,
) -> Path:
    relative = Path(result_file)
    if relative.is_absolute() or ".." in relative.parts:
        raise ComparisonInputError(
            f"{suite_name} contains unsafe result_file path: {result_file}"
        )

    suite_root = suite_path.parent.resolve()
    resolved = (suite_root / relative).resolve()
    try:
        resolved.relative_to(suite_root)
    except ValueError as exc:
        raise ComparisonInputError(
            f"{suite_name} result_file escapes suite directory: {result_file}"
        ) from exc
    return resolved


def _load_suite_entries(
    path: str | Path,
    name: str,
) -> tuple[tuple[_SuiteEntry, ...], SuiteExecutionIdentity]:
    suite_path = Path(path)
    payload = _load_json_object(suite_path, name)
    try:
        execution = validate_suite_execution(payload, name=name)
    except ReproducibilityError as exc:
        raise ComparisonInputError(str(exc)) from exc
    if payload.get("status") != "PASS":
        raise ComparisonInputError(f"{name} must have PASS status before regression comparison")

    raw_scenarios = payload.get("scenarios")
    if not isinstance(raw_scenarios, list) or not raw_scenarios:
        raise ComparisonInputError(f"{name}.scenarios must be a non-empty array")

    entries: list[_SuiteEntry] = []
    seen: set[str] = set()
    for index, raw_entry in enumerate(raw_scenarios):
        if not isinstance(raw_entry, dict):
            raise ComparisonInputError(f"{name}.scenarios[{index}] must be an object")
        scenario = raw_entry.get("scenario")
        result_file = raw_entry.get("result_file")
        status = raw_entry.get("status")
        if not isinstance(scenario, str) or not scenario:
            raise ComparisonInputError(
                f"{name}.scenarios[{index}].scenario must be a non-empty string"
            )
        if scenario in seen:
            raise ComparisonInputError(f"{name} contains duplicate scenario '{scenario}'")
        if status != "PASS":
            raise ComparisonInputError(
                f"{name} scenario '{scenario}' must have PASS status before comparison"
            )
        if not isinstance(result_file, str) or not result_file:
            raise ComparisonInputError(
                f"{name}.scenarios[{index}].result_file must be a non-empty string"
            )
        seen.add(scenario)
        entries.append(
            _SuiteEntry(
                scenario=scenario,
                result_path=_safe_result_path(
                    suite_path=suite_path,
                    result_file=result_file,
                    suite_name=name,
                ),
            )
        )

    return tuple(entries), execution


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
    baseline_entries, baseline_execution = _load_suite_entries(
        baseline_path, "baseline suite"
    )
    candidate_entries, candidate_execution = _load_suite_entries(
        candidate_path, "candidate suite"
    )
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
        baseline_snapshot = load_scenario_result(baseline_entry.result_path)
        candidate_snapshot = load_scenario_result(candidate_entry.result_path)
        if baseline_snapshot.scenario != baseline_entry.scenario:
            raise ComparisonInputError(
                f"baseline suite scenario '{baseline_entry.scenario}' points to result "
                f"for '{baseline_snapshot.scenario}'"
            )
        if candidate_snapshot.scenario != candidate_entry.scenario:
            raise ComparisonInputError(
                f"candidate suite scenario '{candidate_entry.scenario}' points to result "
                f"for '{candidate_snapshot.scenario}'"
            )

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
