from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from robotci.scaffold import ScaffoldError, initialize_project

app = typer.Typer(
    name="robotci-init",
    help="Create a safe starter RobotCI configuration in an existing project.",
    invoke_without_command=True,
    no_args_is_help=False,
    add_completion=False,
)
console = Console()


@app.callback(invoke_without_command=True)
def init_command(
    project_root: Annotated[
        Path,
        typer.Option(
            "--project-root",
            "-p",
            help="Existing project directory where robotci.yaml should be created.",
            file_okay=False,
            dir_okay=True,
            readable=True,
            writable=True,
        ),
    ] = Path("."),
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            "-f",
            help="Explicitly replace an existing robotci.yaml.",
        ),
    ] = False,
) -> None:
    """Create a validated starter configuration and print the next local steps."""
    try:
        result = initialize_project(project_root, force=force)
    except ScaffoldError as exc:
        console.print(f"[red]RobotCI init error:[/red] {exc}")
        raise typer.Exit(code=3) from exc

    action = "Replaced" if result.replaced else "Created"
    console.print(f"[green]{action}[/green] {result.config_path}")
    console.print("Starter scenario: smoke_route (0,0 → 1,0)")
    console.print("Edit the coordinates for your simulation before the first real run.")
    console.print()
    console.print("Next:")
    console.print(f"  1. robotci validate --config {result.config_path}", markup=False)
    console.print("  2. robotci doctor", markup=False)
    console.print(f"  3. robotci run --config {result.config_path}", markup=False)


if __name__ == "__main__":
    app()
