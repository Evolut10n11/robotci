from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from robotci.cli import app, console
from robotci.viewer import (
    DEFAULT_VIEWER_HOST,
    DEFAULT_VIEWER_PORT,
    ViewerError,
    demo_replay,
    load_replay,
    serve_viewer,
)


@app.command("view")
def view_command(
    replay: Annotated[
        Path | None,
        typer.Option(
            "--replay",
            "-r",
            help="Replay v1 JSON artifact to display.",
        ),
    ] = None,
    demo: Annotated[
        bool,
        typer.Option(
            "--demo",
            help="Open a deterministic built-in replay.",
        ),
    ] = False,
    host: Annotated[
        str,
        typer.Option(
            "--host",
            help="Local interface used by the viewer server.",
        ),
    ] = DEFAULT_VIEWER_HOST,
    port: Annotated[
        int,
        typer.Option(
            "--port",
            min=0,
            max=65535,
            help="Local viewer port. Use 0 to choose a free port automatically.",
        ),
    ] = DEFAULT_VIEWER_PORT,
    no_open: Annotated[
        bool,
        typer.Option(
            "--no-open",
            help="Do not open the browser automatically.",
        ),
    ] = False,
) -> None:
    """Open the local 3D Replay v1 viewer."""
    if demo and replay is not None:
        console.print("[red]RobotCI viewer error:[/red] use either --demo or --replay, not both")
        raise typer.Exit(code=3)
    if not demo and replay is None:
        console.print("[red]RobotCI viewer error:[/red] pass --demo or --replay <file.json>")
        raise typer.Exit(code=3)

    try:
        payload = demo_replay() if demo else load_replay(replay)  # type: ignore[arg-type]
        console.print(f"Replay: [cyan]{payload['scenario']}[/cyan]")
        console.print(f"Viewer: http://{host}:{port}/")
        console.print("Press Ctrl+C to stop the local viewer.")
        serve_viewer(
            payload,
            host=host,
            port=port,
            open_browser=not no_open,
        )
    except (ViewerError, OSError) as exc:
        console.print(f"[red]RobotCI viewer error:[/red] {exc}")
        raise typer.Exit(code=3) from exc


if __name__ == "__main__":
    app()
