from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from robotci.comparison import ComparisonInputError
from robotci.regression import RegressionPolicy
from robotci.suite_comparison import compare_suite_result_files
from robotci.suite_reporting import (
    suite_regression_report_payload,
    write_suite_regression_report,
)

console = Console()


def compare_suite_command(
    baseline: Annotated[
        Path,
        typer.Option("--baseline", help="Known-good suite-result.json."),
    ],
    candidate: Annotated[
        Path,
        typer.Option("--candidate", help="Candidate suite-result.json."),
    ],
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print only the machine-readable suite report JSON."),
    ] = False,
    output: Annotated[
        Path | None,
        typer.Option(
            "--output",
            "-o",
            help="Write the machine-readable suite regression report JSON to this path.",
        ),
    ] = None,
    max_duration_increase_pct: Annotated[
        float,
        typer.Option("--max-duration-increase-pct", min=0.0),
    ] = 10.0,
    max_path_length_increase_pct: Annotated[
        float,
        typer.Option("--max-path-length-increase-pct", min=0.0),
    ] = 10.0,
    max_stuck_events_increase: Annotated[
        int,
        typer.Option("--max-stuck-events-increase", min=0),
    ] = 0,
    max_recoveries_increase: Annotated[
        int,
        typer.Option("--max-recoveries-increase", min=0),
    ] = 0,
) -> None:
    """Compare complete candidate and baseline suite results and gate on regressions."""
    try:
        policy = RegressionPolicy(
            max_duration_increase_pct=max_duration_increase_pct,
            max_path_length_increase_pct=max_path_length_increase_pct,
            max_stuck_events_increase=max_stuck_events_increase,
            max_recoveries_increase=max_recoveries_increase,
        )
        report = compare_suite_result_files(
            baseline_path=baseline,
            candidate_path=candidate,
            policy=policy,
        )
    except (ComparisonInputError, ValueError) as exc:
        console.print(f"[red]RobotCI suite comparison error:[/red] {exc}")
        raise typer.Exit(code=3) from exc

    payload = suite_regression_report_payload(
        report=report,
        policy=policy,
        baseline_path=baseline,
        candidate_path=candidate,
    )

    if output is not None:
        try:
            write_suite_regression_report(
                output,
                report=report,
                policy=policy,
                baseline_path=baseline,
                candidate_path=candidate,
            )
        except OSError as exc:
            console.print(f"[red]RobotCI suite comparison error:[/red] cannot write report: {exc}")
            raise typer.Exit(code=3) from exc

    if json_output:
        console.print_json(data=payload)
    else:
        table = Table(title="RobotCI suite regression gate")
        table.add_column("Scenario")
        table.add_column("Verdict")
        table.add_column("Findings", justify="right")
        for item in report.scenarios:
            style = "green" if item.report.status == "PASS" else "red"
            table.add_row(
                item.scenario,
                f"[{style}]{item.report.status}[/{style}]",
                str(len(item.report.findings)),
            )
        console.print(table)
        style = "green" if report.status == "PASS" else "red"
        console.print(f"Suite regression verdict: [{style}]{report.status}[/{style}]")
        if output is not None:
            console.print(f"Report: {output}", soft_wrap=True)

    if report.status == "REGRESSION":
        raise typer.Exit(code=4)


def main() -> None:
    typer.run(compare_suite_command)


if __name__ == "__main__":
    main()
