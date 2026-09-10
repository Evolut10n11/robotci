from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from robotci import __version__
from robotci.doctor import run_doctor_checks

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


if __name__ == "__main__":
    app()
