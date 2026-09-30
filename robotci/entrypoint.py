from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from robotci.baselines import DEFAULT_BASELINE_ROOT, baseline_suite_path
from robotci.cli import app, console
from robotci.regression import RegressionPolicy
from robotci.viewer import (
    DEFAULT_VIEWER_HOST,
    DEFAULT_VIEWER_PORT,
    ViewerError,
    load_replay,
    serve_viewer,
)
from robotci.viewer_session import demo_session, replay_session, suite_session


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
    baseline: Annotated[
        Path | None, typer.Option("--baseline", help="Baseline Replay v1 for visual comparison.")
    ] = None,
    suite: Annotated[
        Path | None,
        typer.Option("--suite", help="Candidate suite-result.json, including sidecar replays."),
    ] = None,
    baseline_suite: Annotated[
        Path | None, typer.Option("--baseline-suite", help="Baseline suite for the verified gate.")
    ] = None,
    baseline_name: Annotated[
        str | None,
        typer.Option("--baseline-name", help="Saved baseline name for comparison with --suite."),
    ] = None,
    baseline_store: Annotated[
        Path | None,
        typer.Option(
            "--baseline-store",
            help="Baseline store for --baseline-name (default: .robotci/baselines).",
        ),
    ] = None,
    scenario: Annotated[
        str | None, typer.Option("--scenario", help="Initially selected scenario in the suite.")
    ] = None,
    demo: Annotated[
        bool,
        typer.Option(
            "--demo",
            help="Open a deterministic built-in replay.",
        ),
    ] = False,
    max_duration_increase_pct: Annotated[
        float, typer.Option(min=0, help="Allowed duration increase for suite comparison (%).")
    ] = 10.0,
    max_path_length_increase_pct: Annotated[
        float, typer.Option(min=0, help="Allowed path length increase for suite comparison (%).")
    ] = 10.0,
    max_distance_to_goal_increase_m: Annotated[
        float, typer.Option(min=0, help="Allowed goal-distance increase for suite comparison (m).")
    ] = 0.1,
    max_stuck_events_increase: Annotated[
        int, typer.Option(min=0, help="Allowed additional stuck events for suite comparison.")
    ] = 0,
    max_recoveries_increase: Annotated[
        int, typer.Option(min=0, help="Allowed additional recoveries for suite comparison.")
    ] = 0,
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
    if sum((demo, replay is not None, suite is not None)) != 1:
        console.print(
            "[red]RobotCI viewer error:[/red] pass --demo or --replay <file.json> "
            "or --suite <suite-result.json>; select exactly one source"
        )
        raise typer.Exit(code=3)

    try:
        if baseline is not None and replay is None:
            raise ViewerError("--baseline requires --replay")
        if suite is None and any(
            value is not None for value in (baseline_suite, baseline_name, scenario)
        ):
            raise ViewerError("--baseline-suite, --baseline-name and --scenario require --suite")
        if baseline_suite is not None and baseline_name is not None:
            raise ViewerError("use either --baseline-name or --baseline-suite, not both")
        if baseline_store is not None and baseline_name is None:
            raise ViewerError("--baseline-store requires --baseline-name")
        if baseline_name is not None:
            baseline_suite = baseline_suite_path(
                baseline_name,
                store_root=baseline_store if baseline_store is not None else DEFAULT_BASELINE_ROOT,
            )
        if demo:
            session = demo_session()
        elif suite is not None:
            session = suite_session(
                suite,
                baseline_suite,
                scenario=scenario,
                policy=RegressionPolicy(
                    max_duration_increase_pct=max_duration_increase_pct,
                    max_path_length_increase_pct=max_path_length_increase_pct,
                    max_distance_to_goal_increase_m=max_distance_to_goal_increase_m,
                    max_stuck_events_increase=max_stuck_events_increase,
                    max_recoveries_increase=max_recoveries_increase,
                ),
            )
        else:
            assert replay is not None
            session = replay_session(
                load_replay(replay),
                load_replay(baseline) if baseline else None,
                candidate_label=replay.name,
                baseline_label=baseline.name if baseline else "Baseline recording",
            )
        selected = next(
            item for item in session["scenarios"] if item["name"] == session["selected_scenario"]
        )
        payload = selected["candidate"]["replay"]
        console.print(f"Replay: [cyan]{session['selected_scenario']}[/cyan]")

        def viewer_ready(url: str) -> None:
            console.print(f"Viewer: {url}", markup=False)
            console.print("Press Ctrl+C to stop the local viewer.")

        serve_viewer(
            payload,
            host=host,
            port=port,
            open_browser=not no_open,
            session=session,
            on_ready=viewer_ready,
        )
    except (ValueError, OSError) as exc:
        console.print(f"[red]RobotCI viewer error:[/red] {exc}")
        raise typer.Exit(code=3) from exc


if __name__ == "__main__":
    app()
