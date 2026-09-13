from __future__ import annotations

import json
import math
import xml.etree.ElementTree as ET
from pathlib import Path

from robotci.regression import RegressionFinding, RegressionPolicy, RegressionReport
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


def _format_junit_finding(finding: RegressionFinding) -> str:
    increase = "unbounded" if not math.isfinite(finding.increase) else str(finding.increase)
    return (
        f"{finding.metric}: baseline={finding.baseline}, candidate={finding.candidate}, "
        f"increase={increase}, allowed={finding.allowed_increase} {finding.unit}"
    )


def suite_regression_junit_xml(
    *,
    report: SuiteRegressionReport,
    baseline_path: str | Path,
    candidate_path: str | Path,
) -> str:
    """Render suite regression verdicts as portable JUnit XML."""
    failures = sum(item.report.status == "REGRESSION" for item in report.scenarios)
    suite = ET.Element(
        "testsuite",
        {
            "name": "RobotCI suite regression",
            "tests": str(len(report.scenarios)),
            "failures": str(failures),
            "errors": "0",
        },
    )
    properties = ET.SubElement(suite, "properties")
    ET.SubElement(properties, "property", {"name": "baseline", "value": str(baseline_path)})
    ET.SubElement(properties, "property", {"name": "candidate", "value": str(candidate_path)})
    ET.SubElement(properties, "property", {"name": "robotci_status", "value": report.status})

    for item in report.scenarios:
        case = ET.SubElement(
            suite,
            "testcase",
            {
                "name": item.scenario,
                "classname": "robotci.regression",
            },
        )
        if item.report.status == "REGRESSION":
            failure = ET.SubElement(
                case,
                "failure",
                {
                    "type": "REGRESSION",
                    "message": f"{len(item.report.findings)} regression finding(s)",
                },
            )
            failure.text = "\n".join(
                _format_junit_finding(finding) for finding in item.report.findings
            )
        system_out = ET.SubElement(case, "system-out")
        system_out.text = (
            f"baseline_result={item.baseline_result}\n"
            f"candidate_result={item.candidate_result}\n"
        )

    ET.indent(suite, space="  ")
    return ET.tostring(suite, encoding="unicode")


def write_suite_regression_junit(
    path: str | Path,
    *,
    report: SuiteRegressionReport,
    baseline_path: str | Path,
    candidate_path: str | Path,
) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = suite_regression_junit_xml(
        report=report,
        baseline_path=baseline_path,
        candidate_path=candidate_path,
    )
    output_path.write_text(f"{payload}\n", encoding="utf-8")
    return output_path
