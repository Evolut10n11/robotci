from __future__ import annotations

import json
import math
from pathlib import Path

from robotci.regression import RegressionPolicy, RegressionReport
from robotci.suite_comparison import SuiteRegressionReport

SUITE_REPORT_SCHEMA_VERSION = 1


def _findings_payload(report: RegressionReport) -> list[dict[str, object]]:
    return [
        {
            "metric": finding.metric,
            "baseline": finding.baseline,
            "candidate": finding.candidate,
            "increase": finding.increase if math.isfinite(finding.increase) else None,
            "increase_unbounded": not math.isfinite(finding.increase),
            "allowed_increase": finding.allowed_increase,
            "unit": finding.unit,
        }
        for finding in report.findings
    ]


def suite_regression_report_payload(
    *,
    report: SuiteRegressionReport,
    policy: RegressionPolicy,
    baseline_path: str | Path,
    candidate_path: str | Path,
) -> dict[str, object]:
    return {
        "schema_version": SUITE_REPORT_SCHEMA_VERSION,
        "kind": "suite_regression",
        "status": report.status,
        "baseline": str(baseline_path),
        "candidate": str(candidate_path),
        "policy": {
            "max_duration_increase_pct": policy.max_duration_increase_pct,
            "max_path_length_increase_pct": policy.max_path_length_increase_pct,
            "max_stuck_events_increase": policy.max_stuck_events_increase,
            "max_recoveries_increase": policy.max_recoveries_increase,
        },
        "scenarios": [
            {
                "scenario": item.scenario,
                "status": item.report.status,
                "baseline_result": str(item.baseline_result),
                "candidate_result": str(item.candidate_result),
                "findings": _findings_payload(item.report),
            }
            for item in report.scenarios
        ],
    }


def suite_regression_report_json(
    *,
    report: SuiteRegressionReport,
    policy: RegressionPolicy,
    baseline_path: str | Path,
    candidate_path: str | Path,
) -> str:
    return json.dumps(
        suite_regression_report_payload(
            report=report,
            policy=policy,
            baseline_path=baseline_path,
            candidate_path=candidate_path,
        ),
        indent=2,
        sort_keys=True,
        allow_nan=False,
    )


def _format_delta(value: float, unit: str) -> str:
    if math.isfinite(value):
        suffix = f" {unit}" if unit else ""
        return f"{value:+.2f}{suffix}"
    return "unbounded"


def suite_regression_report_markdown(
    *,
    report: SuiteRegressionReport,
    policy: RegressionPolicy,
    baseline_path: str | Path,
    candidate_path: str | Path,
) -> str:
    icon = "✅" if report.status == "PASS" else "❌"
    lines = [
        "## RobotCI suite regression gate",
        "",
        f"{icon} **{report.status}** — compared `{candidate_path}` against `{baseline_path}`.",
        "",
        "| Scenario | Verdict | Findings |",
        "| --- | --- | ---: |",
    ]
    for item in report.scenarios:
        verdict_icon = "✅" if item.report.status == "PASS" else "❌"
        lines.append(
            f"| `{item.scenario}` | {verdict_icon} {item.report.status} | "
            f"{len(item.report.findings)} |"
        )

    regression_items = [item for item in report.scenarios if item.report.findings]
    if regression_items:
        lines.extend(["", "### Regression details", ""])
        for item in regression_items:
            lines.append(f"#### `{item.scenario}`")
            lines.append("")
            for finding in item.report.findings:
                delta = _format_delta(finding.increase, finding.unit)
                allowed = _format_delta(finding.allowed_increase, finding.unit)
                lines.append(
                    f"- `{finding.metric}`: baseline `{finding.baseline:g}`, "
                    f"candidate `{finding.candidate:g}`, change **{delta}** "
                    f"(allowed {allowed})"
                )
            lines.append("")

    lines.extend(
        [
            "### Policy",
            "",
            f"- duration: +{policy.max_duration_increase_pct:g}% max",
            f"- path length: +{policy.max_path_length_increase_pct:g}% max",
            f"- stuck events: +{policy.max_stuck_events_increase} max",
            f"- recoveries: +{policy.max_recoveries_increase} max",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def write_suite_regression_report(
    path: str | Path,
    *,
    report: SuiteRegressionReport,
    policy: RegressionPolicy,
    baseline_path: str | Path,
    candidate_path: str | Path,
) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = suite_regression_report_json(
        report=report,
        policy=policy,
        baseline_path=baseline_path,
        candidate_path=candidate_path,
    )
    output_path.write_text(f"{payload}\n", encoding="utf-8")
    return output_path


def write_suite_regression_markdown(
    path: str | Path,
    *,
    report: SuiteRegressionReport,
    policy: RegressionPolicy,
    baseline_path: str | Path,
    candidate_path: str | Path,
) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        suite_regression_report_markdown(
            report=report,
            policy=policy,
            baseline_path=baseline_path,
            candidate_path=candidate_path,
        ),
        encoding="utf-8",
    )
    return output_path
