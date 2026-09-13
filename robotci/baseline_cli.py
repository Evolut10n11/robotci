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

app = typer.Typer(
    name="robotci-baseline",
    help="Capture and manage local known-good RobotCI suite baselines.",
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
