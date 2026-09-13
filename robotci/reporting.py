from __future__ import annotations

import json
import math
from pathlib import Path

from robotci.regression import RegressionPolicy, RegressionReport

REPORT_SCHEMA_VERSION = 1


def _json_number(value: float) -> float | None:
    """Return a strict-JSON number, replacing infinity with null."""
    return value if math.isfinite(value) else None


def regression_report_payload(
    *,
    report: RegressionReport,
    policy: RegressionPolicy,
    baseline_path: str | Path,
    candidate_path: str | Path,
) -> dict[str, object]:
    """Build the stable machine-readable representation of a comparison verdict."""
    findings = [
        {
            "metric": finding.metric,
            "baseline": finding.baseline,
            "candidate": finding.candidate,
            "increase": _json_number(finding.increase),
            "increase_unbounded": not math.isfinite(finding.increase),
            "allowed_increase": finding.allowed_increase,
            "unit": finding.unit,
        }
        for finding in report.findings
    ]

    return {
        "schema_version": REPORT_SCHEMA_VERSION,
        "status": report.status,
        "baseline": str(baseline_path),
        "candidate": str(candidate_path),
        "policy": {
            "max_duration_increase_pct": policy.max_duration_increase_pct,
            "max_path_length_increase_pct": policy.max_path_length_increase_pct,
            "max_stuck_events_increase": policy.max_stuck_events_increase,
            "max_recoveries_increase": policy.max_recoveries_increase,
        },
        "findings": findings,
    }


def regression_report_json(
    *,
    report: RegressionReport,
    policy: RegressionPolicy,
    baseline_path: str | Path,
    candidate_path: str | Path,
) -> str:
    """Serialize a comparison report as strict JSON suitable for CI artifacts."""
    return json.dumps(
        regression_report_payload(
            report=report,
            policy=policy,
            baseline_path=baseline_path,
            candidate_path=candidate_path,
        ),
        indent=2,
        sort_keys=True,
        allow_nan=False,
    )


def write_regression_report(
    path: str | Path,
    *,
    report: RegressionReport,
    policy: RegressionPolicy,
    baseline_path: str | Path,
    candidate_path: str | Path,
) -> Path:
    """Persist a strict-JSON comparison report and return the written path."""
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = regression_report_json(
        report=report,
        policy=policy,
        baseline_path=baseline_path,
        candidate_path=candidate_path,
    )
    output_path.write_text(f"{payload}\n", encoding="utf-8")
    return output_path
