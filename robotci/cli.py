from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from robotci import __version__
from robotci.doctor import run_doctor_checks
from robotci.runner import RuntimeUnavailableError, read_result_status, run_scenario

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


@app.command("run")
def run_command(
    scenario: Annotated[
        str,
        typer.Option(
            "--scenario",
            "-s",
            help="Scenario to execute.",
        ),
    ] = "simple_route",
    runtime: Annotated[
        str,
        typer.Option(
            "--runtime",
            "-r",
            help="Runtime: auto, native, or docker.",
        ),
    ] = "auto",
    output: Annotated[
        Path,
        typer.Option(
            "--output",
            "-o",
            help="Machine-readable result JSON path.",
        ),
    ] = Path(".robotci/result.json"),
    timeout_sec: Annotated[
        float,
        typer.Option(
            "--timeout-sec",
            min=0.1,
            help="Maximum navigation time in seconds.",
        ),
    ] = 120.0,
) -> None:
    """Run a RobotCI navigation scenario."""
    if runtime not in {"auto", "native", "docker"}:
        console.print(f"[red]RobotCI error:[/red] unsupported runtime '{runtime}'")
        raise typer.Exit(code=3)

    try:
        exit_code, selected_runtime, result_path = run_scenario(
            scenario=scenario,
            runtime=runtime,  # type: ignore[arg-type]
            output=output,
            timeout_sec=timeout_sec,
        )
    except (RuntimeUnavailableError, ValueError) as exc:
        console.print(f"[red]RobotCI runtime error:[/red] {exc}")
        raise typer.Exit(code=3) from exc

    status = read_result_status(result_path)
    console.print(f"Runtime: [cyan]{selected_runtime}[/cyan]")
    if status is not None:
        style = "green" if status == "PASS" else "red"
        console.print(f"Verdict: [{style}]{status}[/{style}]")
    console.print(f"Result: {result_path}", soft_wrap=True)

    if exit_code != 0:
        raise typer.Exit(code=exit_code)


if __name__ == "__main__":
    app()
