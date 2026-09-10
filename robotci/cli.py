from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from robotci import __version__
from robotci.config import ConfigError, load_config
from robotci.doctor import run_doctor_checks
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
        loaded = load_config(config)
    except ConfigError as exc:
        console.print(f"[red]RobotCI config error:[/red] {exc}")
        raise typer.Exit(code=3) from exc

    table = Table(title="RobotCI configuration")
    table.add_column("Scenario")
    table.add_column("Start")
    table.add_column("Goal")
    table.add_column("Timeout")

    for scenario in loaded.scenarios:
        start = f"({scenario.start.x}, {scenario.start.y}, {scenario.start.yaw})"
        goal = f"({scenario.goal.x}, {scenario.goal.y}, {scenario.goal.yaw})"
        table.add_row(scenario.name, start, goal, f"{scenario.timeout_sec:g}s")

    console.print(f"Config: {Path(config)}", soft_wrap=True)
    console.print(f"Runtime: [cyan]{loaded.runtime}[/cyan]")
    console.print(table)
    console.print("[green]Configuration valid[/green]")


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
