from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

import typer
from rich.console import Console
from rich.table import Table

from robotci.baselines import (
    DEFAULT_BASELINE_ROOT,
    BaselineError,
    BaselineInfo,
    baseline_suite_path,
    capture_baseline,
    list_baselines,
    load_baseline_manifest,
    remove_baseline,
)
from robotci.comparison import ComparisonInputError
from robotci.regression import RegressionPolicy
from robotci.suite_comparison import compare_suite_result_files
from robotci.suite_reporting import (
    suite_regression_report_payload,
    write_suite_regression_junit,
    write_suite_regression_markdown,
    write_suite_regression_report,
)

app = typer.Typer(
    name="robotci-baseline",
    help="Capture, inspect, and gate against local known-good RobotCI suite baselines.",
    no_args_is_help=True,
)
console = Console()


def _baseline_payload(info: BaselineInfo) -> dict[str, Any]:
    return {
        "name": info.name,
        "path": str(info.path),
        "captured_at": info.captured_at,
        "source_suite": info.source_suite,
        "suite_file": str(info.path / "suite-result.json"),
        "scenarios": list(info.scenarios),
    }


def _fail(exc: Exception) -> None:
    console.print(f"[red]RobotCI baseline error:[/red] {exc}")
    raise typer.Exit(code=3) from exc


@app.command("save")
def save_baseline_command(
    name: Annotated[str, typer.Argument(help="Baseline name.")],
    suite: Annotated[
        Path,
        typer.Option(
            "--suite",
            help="Successful suite-result.json to capture.",
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
        ),
    ],
    store: Annotated[
        Path,
        typer.Option("--store", help="Baseline store directory."),
    ] = DEFAULT_BASELINE_ROOT,
    replace: Annotated[
        bool,
        typer.Option(
            "--replace",
            help="Explicitly replace an existing baseline with the same name.",
        ),
    ] = False,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print machine-readable baseline metadata JSON."),
    ] = False,
) -> None:
    """Capture a successful suite and every referenced scenario result."""
    try:
        info = capture_baseline(name, suite, store_root=store, replace=replace)
    except (BaselineError, OSError) as exc:
        _fail(exc)

    if json_output:
        console.print_json(data=_baseline_payload(info))
        return

    console.print(f"[green]Saved baseline[/green] {info.name}")
    console.print(f"Path: {info.path}", soft_wrap=True)
    console.print(f"Scenarios: {', '.join(info.scenarios)}")
    console.print(f"Captured: {info.captured_at}")


@app.command("gate")
def gate_baseline_command(
    name: Annotated[str, typer.Argument(help="Saved baseline name.")],
    candidate: Annotated[
        Path,
        typer.Option(
            "--candidate",
            help="Candidate suite-result.json to compare against the saved baseline.",
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
        ),
    ],
    store: Annotated[
        Path,
        typer.Option("--store", help="Baseline store directory."),
    ] = DEFAULT_BASELINE_ROOT,
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
    markdown_output: Annotated[
        Path | None,
        typer.Option(
            "--markdown-output",
            help="Write a human-readable Markdown regression summary to this path.",
        ),
    ] = None,
    junit_output: Annotated[
        Path | None,
        typer.Option(
            "--junit-output",
            help="Write the suite regression verdict as a JUnit XML report.",
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
    """Compare a candidate suite against one saved known-good baseline."""
    try:
        baseline = baseline_suite_path(name, store_root=store)
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
    except (BaselineError, ComparisonInputError, ValueError, OSError) as exc:
        _fail(exc)

    payload = suite_regression_report_payload(
        report=report,
        policy=policy,
        baseline_path=baseline,
        candidate_path=candidate,
    )

    try:
        if output is not None:
            write_suite_regression_report(
                output,
                report=report,
                policy=policy,
                baseline_path=baseline,
                candidate_path=candidate,
            )
        if markdown_output is not None:
            write_suite_regression_markdown(
                markdown_output,
                report=report,
                policy=policy,
                baseline_path=baseline,
                candidate_path=candidate,
            )
        if junit_output is not None:
            write_suite_regression_junit(
                junit_output,
                report=report,
                baseline_path=baseline,
                candidate_path=candidate,
            )
    except OSError as exc:
        _fail(exc)

    if json_output:
        console.print_json(data=payload)
    else:
        table = Table(title=f"RobotCI baseline gate: {name}")
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
        console.print(f"Baseline: {name} ({baseline})", soft_wrap=True)
        if output is not None:
            console.print(f"Report: {output}", soft_wrap=True)
        if markdown_output is not None:
            console.print(f"Markdown summary: {markdown_output}", soft_wrap=True)
        if junit_output is not None:
            console.print(f"JUnit: {junit_output}", soft_wrap=True)

    if report.status == "REGRESSION":
        raise typer.Exit(code=4)


@app.command("list")
def list_baselines_command(
    store: Annotated[
        Path,
        typer.Option("--store", help="Baseline store directory."),
    ] = DEFAULT_BASELINE_ROOT,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print machine-readable baseline metadata JSON."),
    ] = False,
) -> None:
    """List captured baselines in the local store."""
    try:
        baselines = list_baselines(store_root=store)
    except (BaselineError, OSError) as exc:
        _fail(exc)

    if json_output:
        console.print_json(data=[_baseline_payload(info) for info in baselines])
        return

    if not baselines:
        console.print("No baselines found.")
        return

    table = Table(title="RobotCI baselines")
    table.add_column("Name")
    table.add_column("Scenarios", justify="right")
    table.add_column("Captured")
    table.add_column("Source suite")
    for info in baselines:
        table.add_row(
            info.name,
            str(len(info.scenarios)),
            info.captured_at,
            info.source_suite,
        )
    console.print(table)


@app.command("show")
def show_baseline_command(
    name: Annotated[str, typer.Argument(help="Baseline name.")],
    store: Annotated[
        Path,
        typer.Option("--store", help="Baseline store directory."),
    ] = DEFAULT_BASELINE_ROOT,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print machine-readable baseline metadata JSON."),
    ] = False,
) -> None:
    """Show metadata for one captured baseline."""
    try:
        info = load_baseline_manifest(name, store_root=store)
        suite_path = baseline_suite_path(name, store_root=store)
    except (BaselineError, OSError) as exc:
        _fail(exc)

    if json_output:
        console.print_json(data=_baseline_payload(info))
        return

    table = Table(title=f"RobotCI baseline: {info.name}", show_header=False)
    table.add_column("Field", style="bold")
    table.add_column("Value")
    table.add_row("Name", info.name)
    table.add_row("Path", str(info.path))
    table.add_row("Suite", str(suite_path))
    table.add_row("Captured", info.captured_at)
    table.add_row("Source suite", info.source_suite)
    table.add_row("Scenarios", ", ".join(info.scenarios))
    console.print(table)


@app.command("remove")
def remove_baseline_command(
    name: Annotated[str, typer.Argument(help="Baseline name.")],
    store: Annotated[
        Path,
        typer.Option("--store", help="Baseline store directory."),
    ] = DEFAULT_BASELINE_ROOT,
) -> None:
    """Remove one named baseline from the local store."""
    try:
        remove_baseline(name, store_root=store)
    except (BaselineError, OSError) as exc:
        _fail(exc)

    console.print(f"[green]Removed baseline[/green] {name}")


if __name__ == "__main__":
    app()
