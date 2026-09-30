"""Read-only presentation of replay artifacts and the existing suite regression gate."""

from __future__ import annotations

import copy
import math
from dataclasses import asdict
from pathlib import Path
from typing import Any

from robotci.comparison import ComparisonInputError
from robotci.regression import RegressionPolicy
from robotci.replay import default_replay_path
from robotci.result_schema import ValidatedScenarioResult
from robotci.suite_comparison import compare_suite_result_files
from robotci.suite_reporting import suite_regression_report_payload
from robotci.suite_schema import SuiteResultError, ValidatedSuiteResult, load_suite_result
from robotci.viewer import ViewerError, demo_replay, load_replay, validate_replay


def _replay_start(replay: dict[str, Any]) -> dict[str, Any]:
    """Use configured start, which is separate from observed recording samples."""
    if "recording" in replay:
        return replay["world"]["start"]
    return replay["samples"][0]["position"]


def replay_alignment(candidate: dict[str, Any], baseline: dict[str, Any]) -> str | None:
    """Check spatial alignment, without claiming task or environment provenance."""
    if candidate["scenario"] != baseline["scenario"]:
        return "The recordings describe different scenarios."
    if candidate["world"]["frame"] != baseline["world"]["frame"]:
        return "The recordings use different coordinate frames."
    for label, first, second in (
        ("goal", candidate["world"]["goal"], baseline["world"]["goal"]),
        ("start", _replay_start(candidate), _replay_start(baseline)),
    ):
        if any(not math.isclose(first[k], second[k], abs_tol=1e-6) for k in ("x", "y", "z")):
            return f"The recordings have different {label} positions."
    return None


def _replay_run(replay: dict[str, Any], label: str) -> dict[str, Any]:
    return {
        "label": label,
        "status": replay.get("result_status", replay["status"]),
        "runtime": replay["runtime"],
        "metrics": replay["metrics"],
        "replay": replay,
        "replay_notice": None,
    }


def replay_session(
    candidate: dict[str, Any],
    baseline: dict[str, Any] | None = None,
    *,
    candidate_label: str = "Candidate recording",
    baseline_label: str = "Baseline recording",
    demo: bool = False,
) -> dict[str, Any]:
    candidate = validate_replay(candidate)
    if baseline is not None:
        baseline = validate_replay(baseline)
    alignment = replay_alignment(candidate, baseline) if baseline is not None else None
    return {
        "schema_version": 1,
        "source": "demo" if demo else "replay",
        "selected_scenario": candidate["scenario"],
        "candidate_label": candidate_label,
        "baseline_label": baseline_label if baseline else None,
        "gate": None,
        "gate_notice": (
            "Replay files show recorded behavior. A verified gate requires suite results."
        ),
        "scenarios": [
            {
                "name": candidate["scenario"],
                "candidate": _replay_run(candidate, candidate_label),
                "baseline": _replay_run(baseline, baseline_label) if baseline else None,
                "alignment_notice": alignment,
                "comparison": None,
            }
        ],
    }


def demo_session() -> dict[str, Any]:
    candidate = demo_replay()
    baseline = copy.deepcopy(candidate)
    baseline["duration_sec"] = 10.0
    baseline["metrics"] = {
        **baseline["metrics"],
        "duration_sec": 10.0,
        "stuck_events": 0,
        "recoveries": 0,
    }
    for sample in baseline["samples"]:
        sample["t"] = round(sample["t"] * 10 / 12, 3)
        fraction = sample["t"] / 10
        sample["position"]["x"] = round(5 * fraction, 4)
        sample["position"]["y"] = round(3 * fraction, 4)
        sample["orientation"]["yaw"] = math.atan2(3, 5)
    baseline["metrics"]["path_length_m"] = round(math.hypot(5, 3), 3)
    baseline["events"] = [
        {"t": 0.0, "type": "START", "message": "Synthetic baseline started"},
        {"t": 10.0, "type": "GOAL", "message": "Synthetic baseline reached the goal"},
    ]
    return replay_session(
        candidate,
        baseline,
        candidate_label="Demo candidate",
        baseline_label="Demo baseline",
        demo=True,
    )


def replay_matches_result(replay: dict[str, Any], result: ValidatedScenarioResult) -> None:
    """Reject a stale sidecar that disagrees with the result it accompanies."""
    if replay["scenario"] != result.scenario:
        raise ViewerError("replay scenario does not match its result")
    expected_status = "PASS" if result.status == "PASS" else "FAIL"
    if (
        replay["status"] != expected_status
        or replay.get("result_status", result.status) != result.status
    ):
        raise ViewerError("replay status does not match its result")
    if not math.isclose(replay["duration_sec"], result.duration_sec, abs_tol=0.002, rel_tol=1e-6):
        raise ViewerError("replay duration does not match its result")
    if result.task and replay["world"]["frame"] != result.task.frame_id:
        raise ViewerError("replay frame does not match its result")
    for label, position, expected in (
        ("start", _replay_start(replay), result.start),
        ("goal", replay["world"]["goal"], result.goal),
    ):
        if not math.isclose(position["x"], expected.x, abs_tol=1e-6) or not math.isclose(
            position["y"], expected.y, abs_tol=1e-6
        ):
            raise ViewerError(f"replay {label} does not match its result")
    if result.metrics:
        for key in ("path_length_m", "distance_to_goal_m", "stuck_events", "recoveries"):
            if not math.isclose(replay["metrics"][key], getattr(result.metrics, key), abs_tol=1e-6):
                raise ViewerError(f"replay {key} does not match its result")


def _suite_runs(path: Path) -> tuple[ValidatedSuiteResult, dict[str, dict[str, Any]]]:
    try:
        suite = load_suite_result(path)
        runs = {}
        for item in suite.scenarios:
            result = item.result
            replay_path = default_replay_path(item.result_path)
            replay = None
            notice = "No trajectory was recorded for this result. Metrics are still available."
            if replay_path.is_file():
                try:
                    if not replay_path.resolve().is_relative_to(path.resolve().parent):
                        raise ViewerError("replay sidecar is outside the suite directory")
                    replay = load_replay(replay_path)
                    replay_matches_result(replay, result)
                    notice = None
                except ViewerError as exc:
                    replay = None
                    notice = f"Trajectory unavailable: {exc}"
            metrics = asdict(result.metrics) if result.metrics is not None else {}
            metrics["duration_sec"] = result.duration_sec
            runs[item.scenario] = {
                "label": path.parent.name or path.name,
                "status": result.status,
                "runtime": suite.runtime,
                "metrics": metrics,
                "replay": replay,
                "replay_notice": notice,
            }
        return suite, runs
    except SuiteResultError as exc:
        raise ViewerError(str(exc)) from exc


def suite_session(
    candidate_path: Path,
    baseline_path: Path | None = None,
    *,
    scenario: str | None = None,
    policy: RegressionPolicy | None = None,
) -> dict[str, Any]:
    """Load suite evidence and delegate all gate decisions to the existing engine."""
    candidate_suite, candidates = _suite_runs(candidate_path)
    baselines = _suite_runs(baseline_path)[1] if baseline_path is not None else {}
    if scenario is not None and scenario not in candidates:
        raise ViewerError(f"scenario is not present in the candidate suite: {scenario}")
    gate = None
    notice = "Open a baseline suite to evaluate the regression gate."
    if baseline_path is not None:
        try:
            selected_policy = policy or RegressionPolicy()
            report = compare_suite_result_files(
                baseline_path=baseline_path,
                candidate_path=candidate_path,
                policy=selected_policy,
            )
            gate = suite_regression_report_payload(
                report=report,
                policy=selected_policy,
                baseline_path=baseline_path.name,
                candidate_path=candidate_path.name,
            )
            # Report paths are diagnostic metadata, not browser-readable filesystem endpoints.
            for entry in gate["scenarios"]:
                entry["baseline_result"] = Path(entry["baseline_result"]).name
                entry["candidate_result"] = Path(entry["candidate_result"]).name
            notice = None
        except ComparisonInputError as exc:
            notice = f"Gate unavailable: {exc}"
    comparisons = {item["scenario"]: item for item in gate["scenarios"]} if gate else {}
    scenarios = []
    for name, candidate in candidates.items():
        baseline = baselines.get(name)
        alignment = None
        if baseline and baseline["replay"] and candidate["replay"]:
            alignment = replay_alignment(candidate["replay"], baseline["replay"])
        scenarios.append(
            {
                "name": name,
                "candidate": candidate,
                "baseline": baseline,
                "alignment_notice": alignment,
                "comparison": comparisons.get(name),
            }
        )
    return {
        "schema_version": 1,
        "source": "suite",
        "selected_scenario": scenario or candidate_suite.scenarios[0].scenario,
        "candidate_label": candidate_path.parent.name or candidate_path.name,
        "baseline_label": (
            (baseline_path.parent.name or baseline_path.name) if baseline_path else None
        ),
        "gate": gate,
        "gate_notice": notice,
        "scenarios": scenarios,
    }
