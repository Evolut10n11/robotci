from __future__ import annotations

from robotci.application import (
    DiagnosticReport,
    ProjectInfo,
    SuiteResultSnapshot,
)
from robotci.config import PoseConfig, RobotCIConfig, ScenarioConfig
from robotci.evidence import NavigationEvidencePolicy
from robotci.metrics import NavigationMetrics, NavigationTelemetryQuality
from robotci.regression import RegressionFinding, RegressionReport
from robotci.reproducibility import RuntimeEnvironment, SuiteExecutionIdentity
from robotci.result_schema import ValidatedScenarioResult
from robotci.results import Pose2D, ScenarioTaskIdentity
from robotci.suite_comparison import SuiteRegressionReport


def _pose(pose: PoseConfig | Pose2D) -> dict[str, float]:
    return {"x": pose.x, "y": pose.y, "yaw": pose.yaw}


def serialize_scenario(scenario: ScenarioConfig) -> dict[str, object]:
    return {
        "name": scenario.name,
        "start": _pose(scenario.start),
        "goal": _pose(scenario.goal),
        "timeout_sec": scenario.timeout_sec,
        "map_id": scenario.map_id,
        "goal_tolerance_m": scenario.goal_tolerance_m,
        "min_feedback_samples": scenario.min_feedback_samples,
    }


def _config(config: RobotCIConfig) -> dict[str, object]:
    return {
        "version": config.version,
        "runtime": config.runtime,
        "scenarios": [serialize_scenario(scenario) for scenario in config.scenarios],
    }


def serialize_project_info(info: ProjectInfo) -> dict[str, object]:
    return {
        "robotci_version": info.robotci_version,
        "project_root": str(info.project_root),
        "config_path": str(info.config_path),
        "state_path": str(info.state_path),
        "latest_suite_path": str(info.latest_suite_path),
        "config": _config(info.config),
    }


def serialize_diagnostics(report: DiagnosticReport) -> dict[str, object]:
    return {
        "status": report.status,
        "selected_runtime": report.selected_runtime,
        "checks": [
            {
                "name": check.name,
                "ok": check.ok,
                "message": check.message,
                "blocking": check.blocking,
                "value": check.value,
            }
            for check in report.checks
        ],
    }


def _environment(environment: RuntimeEnvironment) -> dict[str, object]:
    return {
        "schema_version": environment.schema_version,
        "os_id": environment.os_id,
        "os_version": environment.os_version,
        "architecture": environment.architecture,
        "python_version": environment.python_version,
        "ros_distro": environment.ros_distro,
        "robotci_build": environment.robotci_build,
        "containerized": environment.containerized,
        "packages": [
            {
                "manager": package.manager,
                "name": package.name,
                "version": package.version,
            }
            for package in environment.packages
        ],
        "runtime_variables": [
            {"name": variable.name, "value": variable.value}
            for variable in environment.runtime_variables
        ],
        "fingerprint": environment.fingerprint,
    }


def _execution(execution: SuiteExecutionIdentity) -> dict[str, object]:
    return {
        "schema_version": execution.schema_version,
        "runtime": execution.runtime,
        "runtime_contract": execution.runtime_contract,
        "plan_fingerprint": execution.plan_fingerprint,
        "environment": _environment(execution.environment),
        "fingerprint": execution.fingerprint,
    }


def serialize_suite_result(suite: SuiteResultSnapshot) -> dict[str, object]:
    return {
        "path": str(suite.path),
        "schema_version": suite.schema_version,
        "status": suite.status,
        "runtime": suite.runtime,
        "duration_sec": suite.duration_sec,
        "scenarios": [
            {
                "scenario": scenario.scenario,
                "status": scenario.status,
                "duration_sec": scenario.duration_sec,
                "result_path": str(scenario.result_path),
            }
            for scenario in suite.scenarios
        ],
        "execution": _execution(suite.execution),
    }


def _metrics(metrics: NavigationMetrics | None) -> dict[str, object] | None:
    if metrics is None:
        return None
    return {
        "path_length_m": metrics.path_length_m,
        "distance_to_goal_m": metrics.distance_to_goal_m,
        "stuck_events": metrics.stuck_events,
        "feedback_samples": metrics.feedback_samples,
        "recoveries": metrics.recoveries,
    }


def _telemetry_quality(
    quality: NavigationTelemetryQuality | None,
) -> dict[str, object] | None:
    if quality is None:
        return None
    return {
        "received_feedback_samples": quality.received_feedback_samples,
        "valid_pose_samples": quality.valid_pose_samples,
        "invalid_pose_samples": quality.invalid_pose_samples,
        "final_pose_valid": quality.final_pose_valid,
    }


def _evidence_policy(
    policy: NavigationEvidencePolicy | None,
) -> dict[str, object] | None:
    if policy is None:
        return None
    return {
        "goal_tolerance_m": policy.goal_tolerance_m,
        "min_feedback_samples": policy.min_feedback_samples,
    }


def _task(task: ScenarioTaskIdentity | None) -> dict[str, object] | None:
    if task is None:
        return None
    return {
        "schema_version": task.schema_version,
        "frame_id": task.frame_id,
        "map_id": task.map_id,
        "fingerprint": task.fingerprint,
    }


def serialize_scenario_result(result: ValidatedScenarioResult) -> dict[str, object]:
    return {
        "source_schema_version": result.source_schema_version,
        "scenario": result.scenario,
        "status": result.status,
        "duration_sec": result.duration_sec,
        "start": _pose(result.start),
        "goal": _pose(result.goal),
        "navigation_result": result.navigation_result,
        "metrics": _metrics(result.metrics),
        "telemetry_quality": _telemetry_quality(result.telemetry_quality),
        "evidence_policy": _evidence_policy(result.evidence_policy),
        "task": _task(result.task),
        "provenance_complete": result.provenance_complete,
        "evidence_complete": result.evidence_complete,
        "reason_code": result.reason_code,
    }


def _finding(finding: RegressionFinding) -> dict[str, object]:
    return {
        "metric": finding.metric,
        "baseline": finding.baseline,
        "candidate": finding.candidate,
        "increase": finding.increase,
        "allowed_increase": finding.allowed_increase,
        "unit": finding.unit,
    }


def _regression_report(report: RegressionReport) -> dict[str, object]:
    return {
        "status": report.status,
        "findings": [_finding(finding) for finding in report.findings],
    }


def serialize_suite_comparison(report: SuiteRegressionReport) -> dict[str, object]:
    return {
        "status": report.status,
        "scenarios": [
            {
                "scenario": scenario.scenario,
                "baseline_result": str(scenario.baseline_result),
                "candidate_result": str(scenario.candidate_result),
                "report": _regression_report(scenario.report),
            }
            for scenario in report.scenarios
        ],
    }
