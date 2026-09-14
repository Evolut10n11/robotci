from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from robotci import __version__
from robotci.comparison import ComparisonInputError, compare_scenario_result_files
from robotci.config import ConfigError, load_config
from robotci.doctor import run_doctor_checks
from robotci.plan import build_execution_plan
from robotci.project import resolve_project_context
from robotci.regression import RegressionPolicy
from robotci.reporting import regression_report_payload, write_regression_report
from robotci.runner import (
    DEFAULT_CONFIG_PATH,
    DEFAULT_RESULT_PATH,
    DEFAULT_SUITE_RESULT_PATH,
    RuntimeUnavailableError,
    read_result_status,
    run_scenario,
    run_suite,
)

app = typer.Typer(
    name="robotci",
    help="Local-first regression testing for ROS2/Nav2.",
    no_args_is_help=True,
)

console = Console()


@app.command()
def version() -> None:
    """Print RobotCI version."""
    console.print(f"RobotCI {__version__}")


@app.command()
def doctor() -> None:
    """Check whether the local machine is ready to run RobotCI."""
    checks = run_doctor_checks()

    table = Table(title="RobotCI environment")
    table.add_column("Check")
    table.add_column("Status")
    table.add_column("Details")

    failed = False
    for check in checks:
        if check.ok:
            status = "[green]PASS[/green]"
        elif check.blocking:
            status = "[red]FAIL[/red]"
            failed = True
        else:
            status = "[yellow]WARN[/yellow]"

        table.add_row(check.name, status, check.message)

    console.print(table)

    if failed:
        raise typer.Exit(code=1)


@app.command("validate")
def validate_command(
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            "-c",
            help="Path to robotci.yaml.",
        ),
    ] = DEFAULT_CONFIG_PATH,
) -> None:
    """Validate RobotCI YAML configuration without starting ROS."""
    try:
        context = resolve_project_context(config)
        loaded = load_config(context.config_path)
    except ConfigError as exc:
        console.print(f"[red]RobotCI config error:[/red] {exc}")
        raise typer.Exit(code=3) from exc

    table = Table(title="RobotCI configuration")
    table.add_column("Scenario", no_wrap=True)
    table.add_column("Start")
    table.add_column("Goal")
    table.add_column("Timeout")

    for scenario in loaded.scenarios:
        start = f"({scenario.start.x}, {scenario.start.y}, {scenario.start.yaw})"
        goal = f"({scenario.goal.x}, {scenario.goal.y}, {scenario.goal.yaw})"
        table.add_row(
            scenario.name,
            start,
            goal,
            f"{scenario.timeout_sec:g}s",
        )

    console.print(f"Config: {context.config_path}", soft_wrap=True)
    console.print(f"Runtime: [cyan]{loaded.runtime}[/cyan]")
    console.print(table)
    for scenario in loaded.scenarios:
        console.print(
            f"PASS evidence {scenario.name}: goal <= "
            f"{scenario.goal_tolerance_m:g}m; feedback >= "
            f"{scenario.min_feedback_samples}"
        )
    console.print("[green]Configuration valid[/green]")


@app.command("plan")
def plan_command(
    scenario: Annotated[
        str | None,
        typer.Option(
            "--scenario",
            "-s",
            help="Show one configured scenario. Omit to show the full suite.",
        ),
    ] = None,
    runtime: Annotated[
        str | None,
        typer.Option(
            "--runtime",
            "-r",
            help="Override config runtime: auto, native, or docker.",
        ),
    ] = None,
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            "-c",
            help="Path to robotci.yaml.",
        ),
    ] = DEFAULT_CONFIG_PATH,
    timeout_sec: Annotated[
        float | None,
        typer.Option(
            "--timeout-sec",
            min=0.1,
            help="Override configured timeout in the resolved plan.",
        ),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Print the resolved plan as machine-readable JSON.",
        ),
    ] = False,
) -> None:
    """Resolve what RobotCI would run without starting ROS or Docker."""
    if runtime is not None and runtime not in {"auto", "native", "docker"}:
        console.print(f"[red]RobotCI error:[/red] unsupported runtime '{runtime}'")
        raise typer.Exit(code=3)

    try:
        plan = build_execution_plan(
            config_path=config,
            scenario=scenario,
            runtime=runtime,  # type: ignore[arg-type]
            timeout_sec=timeout_sec,
        )
    except ConfigError as exc:
        console.print(f"[red]RobotCI config error:[/red] {exc}")
        raise typer.Exit(code=3) from exc

    if json_output:
        console.print_json(data=plan.as_dict())
        return

    table = Table(title="RobotCI execution plan")
    table.add_column("Scenario", no_wrap=True)
    table.add_column("Map")
    table.add_column("Start")
    table.add_column("Goal")
    table.add_column("Timeout")

    for planned in plan.scenarios:
        start = f"({planned.start.x}, {planned.start.y}, {planned.start.yaw})"
        goal = f"({planned.goal.x}, {planned.goal.y}, {planned.goal.yaw})"
        table.add_row(
            planned.name,
            planned.map_id or "unspecified",
            start,
            goal,
            f"{planned.timeout_sec:g}s",
        )

    console.print(f"Config: {plan.config_path}", soft_wrap=True)
    console.print(f"Runtime request: [cyan]{plan.runtime}[/cyan]")
    console.print(table)
    for planned in plan.scenarios:
        console.print(
            f"PASS evidence {planned.name}: goal <= "
            f"{planned.goal_tolerance_m:g}m; feedback >= "
            f"{planned.min_feedback_samples}"
        )
    console.print("[green]Plan resolved; no runtime started[/green]")


@app.command("compare")
def compare_command(
    baseline: Annotated[
        Path,
        typer.Option(
            "--baseline",
            help="Known-good scenario result JSON.",
        ),
    ],
    candidate: Annotated[
        Path,
        typer.Option(
            "--candidate",
            help="Candidate scenario result JSON.",
        ),
    ],
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Print only the machine-readable regression report JSON.",
        ),
    ] = False,
    output: Annotated[
        Path | None,
        typer.Option(
            "--output",
            "-o",
            help="Write the machine-readable regression report JSON to this path.",
        ),
    ] = None,
    max_duration_increase_pct: Annotated[
        float,
        typer.Option(
            "--max-duration-increase-pct",
            min=0.0,
            help="Maximum allowed duration increase in percent.",
        ),
    ] = 10.0,
    max_path_length_increase_pct: Annotated[
        float,
        typer.Option(
            "--max-path-length-increase-pct",
            min=0.0,
            help="Maximum allowed path-length increase in percent.",
        ),
    ] = 10.0,
    max_distance_to_goal_increase_m: Annotated[
        float,
        typer.Option(
            "--max-distance-to-goal-increase-m",
            min=0.0,
            help="Maximum allowed increase in final distance to goal, in meters.",
        ),
    ] = 0.1,
    max_stuck_events_increase: Annotated[
        int,
        typer.Option(
            "--max-stuck-events-increase",
            min=0,
            help="Maximum allowed additional stuck events.",
        ),
    ] = 0,
    max_recoveries_increase: Annotated[
        int,
        typer.Option(
            "--max-recoveries-increase",
            min=0,
            help="Maximum allowed additional recoveries.",
        ),
    ] = 0,
) -> None:
    """Compare one candidate scenario result with a known-good baseline."""
    try:
        policy = RegressionPolicy(
            max_duration_increase_pct=max_duration_increase_pct,
            max_path_length_increase_pct=max_path_length_increase_pct,
            max_distance_to_goal_increase_m=max_distance_to_goal_increase_m,
            max_stuck_events_increase=max_stuck_events_increase,
            max_recoveries_increase=max_recoveries_increase,
        )
        report = compare_scenario_result_files(
            baseline_path=baseline,
            candidate_path=candidate,
            policy=policy,
        )
    except (ComparisonInputError, ValueError) as exc:
        console.print(f"[red]RobotCI comparison error:[/red] {exc}")
        raise typer.Exit(code=3) from exc

    payload = regression_report_payload(
        report=report,
        policy=policy,
        baseline_path=baseline,
        candidate_path=candidate,
    )

    if output is not None:
        try:
            write_regression_report(
                output,
                report=report,
                policy=policy,
                baseline_path=baseline,
                candidate_path=candidate,
            )
        except OSError as exc:
            console.print(f"[red]RobotCI comparison error:[/red] cannot write report: {exc}")
            raise typer.Exit(code=3) from exc

    if json_output:
        console.print_json(data=payload)
    else:
        console.print(f"Baseline: {baseline}", soft_wrap=True)
        console.print(f"Candidate: {candidate}", soft_wrap=True)

        if report.findings:
            table = Table(title="Navigation regressions")
            table.add_column("Metric")
            table.add_column("Baseline", justify="right")
            table.add_column("Candidate", justify="right")
            table.add_column("Increase", justify="right")
            table.add_column("Allowed", justify="right")

            for finding in report.findings:
                suffix = {"percent": "%", "m": "m", "count": ""}[finding.unit]
                table.add_row(
                    finding.metric,
                    f"{finding.baseline:g}",
                    f"{finding.candidate:g}",
                    f"{finding.increase:g}{suffix}",
                    f"{finding.allowed_increase:g}{suffix}",
                )
            console.print(table)

        style = "green" if report.status == "PASS" else "red"
        console.print(f"Regression verdict: [{style}]{report.status}[/{style}]")
        if output is not None:
            console.print(f"Report: {output}", soft_wrap=True)

    if report.status == "REGRESSION":
        raise typer.Exit(code=4)


@app.command("run")
def run_command(
    scenario: Annotated[
        str | None,
        typer.Option(
            "--scenario",
            "-s",
            help="Run one configured scenario. Omit to run the full suite.",
        ),
    ] = None,
    runtime: Annotated[
        str | None,
        typer.Option(
            "--runtime",
            "-r",
            help="Override config runtime: auto, native, or docker.",
        ),
    ] = None,
    config: Annotated[
        Path,
        typer.Option(
            "--config",
            "-c",
            help="Path to robotci.yaml.",
        ),
    ] = DEFAULT_CONFIG_PATH,
    output: Annotated[
        Path | None,
        typer.Option(
            "--output",
            "-o",
            help="Machine-readable result JSON path.",
        ),
    ] = None,
    timeout_sec: Annotated[
        float | None,
        typer.Option(
            "--timeout-sec",
            min=0.1,
            help="Override configured timeout for one or all scenarios.",
        ),
    ] = None,
) -> None:
    """Run one configured scenario or the complete robotci.yaml suite."""
    if runtime is not None and runtime not in {"auto", "native", "docker"}:
        console.print(f"[red]RobotCI error:[/red] unsupported runtime '{runtime}'")
        raise typer.Exit(code=3)

    try:
        if scenario is None:
            result_output = output or DEFAULT_SUITE_RESULT_PATH
            exit_code, selected_runtime, result_path = run_suite(
                runtime=runtime,  # type: ignore[arg-type]
                output=result_output,
                timeout_sec=timeout_sec,
                config_path=config,
            )
            label = "Suite verdict"
        else:
            result_output = output or DEFAULT_RESULT_PATH
            exit_code, selected_runtime, result_path = run_scenario(
                scenario=scenario,
                runtime=runtime,  # type: ignore[arg-type]
                output=result_output,
                timeout_sec=timeout_sec,
                config_path=config,
            )
            label = "Verdict"
    except ConfigError as exc:
        console.print(f"[red]RobotCI config error:[/red] {exc}")
        raise typer.Exit(code=3) from exc
    except (RuntimeUnavailableError, ValueError) as exc:
        console.print(f"[red]RobotCI runtime error:[/red] {exc}")
        raise typer.Exit(code=3) from exc

    status = read_result_status(result_path)
    console.print(f"Runtime: [cyan]{selected_runtime}[/cyan]")
    if status is not None:
        style = "green" if status == "PASS" else "red"
        console.print(f"{label}: [{style}]{status}[/{style}]")
    console.print(f"Result: {result_path}", soft_wrap=True)

    if exit_code != 0:
        raise typer.Exit(code=exit_code)


if __name__ == "__main__":
    app()
