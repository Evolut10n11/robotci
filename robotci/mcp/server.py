from __future__ import annotations

import argparse
import os
from collections.abc import Callable, Mapping, Sequence
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from mcp import MCPError
from mcp.server import MCPServer
from mcp.types import INTERNAL_ERROR, ToolAnnotations

from robotci import __version__
from robotci.application import ApplicationError, RobotCIApplication
from robotci.execution import DEFAULT_MAX_RUN_SEC, ExecutionError, ExecutionManager
from robotci.mcp.serializers import (
    serialize_diagnostics,
    serialize_project_info,
    serialize_scenario,
    serialize_scenario_result,
    serialize_suite_comparison,
    serialize_suite_result,
)

PROJECT_ROOT_ENV = "ROBOTCI_PROJECT_ROOT"


def resolve_project_root(
    project_root: str | Path | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> Path:
    """Resolve the explicit CLI root, environment root, or current directory."""

    environment = os.environ if environ is None else environ
    selected = project_root if project_root is not None else environment.get(PROJECT_ROOT_ENV)
    return (Path.cwd() if selected is None else Path(selected).expanduser()).resolve()


def _call_application[T](
    operation: Callable[[], T],
    serializer: Callable[[T], dict[str, object]],
) -> dict[str, object]:
    try:
        return serializer(operation())
    except (ApplicationError, ExecutionError) as exc:
        raise MCPError(
            code=INTERNAL_ERROR,
            message=str(exc),
            data=exc.as_dict(),
        ) from None
    except ValueError as exc:
        # Expected invalid configuration/baseline/comparison input is a tool
        # diagnostic, not an SDK traceback or a robot-behavior FAIL.
        raise MCPError(
            code=INTERNAL_ERROR, message=str(exc),
            data={"code": "invalid_input", "message": str(exc)},
        ) from None


def create_server(
    application: RobotCIApplication, execution_manager: ExecutionManager | None = None,
) -> MCPServer:
    """Expose inspection by default; execution requires explicit server opt-in."""

    @asynccontextmanager
    async def lifespan(_server):
        try:
            yield {}
        finally:
            if execution_manager is not None:
                execution_manager.close()

    server = MCPServer(
        "robotci",
        description=(
            "Local RobotCI simulation jobs and inspection" if execution_manager
            else "Read-only local RobotCI project inspection"
        ),
        version=__version__,
        log_level="WARNING",
        lifespan=lifespan,
    )

    @server.tool()
    def project_info() -> dict[str, object]:
        """Return RobotCI project paths, version, and effective configuration."""

        return _call_application(application.get_project_info, serialize_project_info)

    @server.tool()
    def list_scenarios() -> dict[str, object]:
        """List the scenarios configured for this RobotCI project."""

        return _call_application(
            application.list_scenarios,
            lambda scenarios: {
                "scenarios": [serialize_scenario(scenario) for scenario in scenarios]
            },
        )

    @server.tool()
    def doctor() -> dict[str, object]:
        """Return structured RobotCI environment diagnostics without running scenarios."""

        return _call_application(application.get_diagnostics, serialize_diagnostics)

    @server.tool()
    def get_latest_suite() -> dict[str, object]:
        """Return the latest validated RobotCI suite result."""

        return _call_application(application.get_latest_suite_result, serialize_suite_result)

    @server.tool()
    def get_scenario_result(scenario: str) -> dict[str, object]:
        """Return one validated scenario result from the latest suite."""

        return _call_application(
            lambda: application.get_scenario_result(scenario),
            serialize_scenario_result,
        )

    @server.tool()
    def compare_to_baseline(name: str) -> dict[str, object]:
        """Compare the latest suite with a named local baseline."""

        return _call_application(
            lambda: application.compare_to_baseline(name),
            serialize_suite_comparison,
        )

    if execution_manager is not None:
        execution_hint = ToolAnnotations(read_only_hint=False, destructive_hint=False)
        inspection_hint = ToolAnnotations(read_only_hint=True, destructive_hint=False)

        @server.tool(annotations=execution_hint)
        def run_suite(runtime: Literal["native", "docker"]) -> dict[str, object]:
            """Start the configured simulation suite as one bounded, isolated owned job."""
            return _call_application(
                lambda: execution_manager.start(runtime=runtime), lambda payload: payload,
            )

        @server.tool(annotations=inspection_hint)
        def get_run(run_id: str) -> dict[str, object]:
            """Read state and completed evidence paths of a job owned by this server."""
            return _call_application(lambda: execution_manager.get(run_id), lambda payload: payload)

        @server.tool(annotations=execution_hint)
        def cancel_run(run_id: str) -> dict[str, object]:
            """Request bounded cleanup of this server's own job; accepts no process ID."""
            return _call_application(
                lambda: execution_manager.cancel(run_id), lambda payload: payload,
            )

        @server.tool(annotations=inspection_hint)
        def compare_run_to_baseline(run_id: str, name: str) -> dict[str, object]:
            """Deterministically compare a completed owned run with an existing baseline."""
            return _call_application(
                lambda: execution_manager.compare(run_id, name), lambda payload: payload,
            )

    return server


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the read-only RobotCI MCP server.")
    parser.add_argument(
        "--project-root",
        type=Path,
        help=f"RobotCI project root (default: ${PROJECT_ROOT_ENV} or current directory).",
    )
    parser.add_argument(
        "--config", type=Path, help="Selected project config (default: robotci.yaml).",
    )
    parser.add_argument(
        "--allow-execution", action="store_true",
        help="Enable owned simulation jobs; requires explicit --project-root and --config.",
    )
    parser.add_argument(
        "--max-run-sec", type=float, default=DEFAULT_MAX_RUN_SEC,
        help="Upper limit on each managed suite budget (default: 3600 seconds).",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.allow_execution and (args.project_root is None or args.config is None):
        parser.error("--allow-execution requires explicit --project-root and --config")
    project_root = resolve_project_root(args.project_root)
    application = RobotCIApplication(
        args.config if args.config is not None else Path("robotci.yaml"), project_root=project_root,
    )
    try:
        manager = (
            ExecutionManager(application, max_run_sec=args.max_run_sec)
            if args.allow_execution else None
        )
    except ExecutionError as exc:
        parser.error(str(exc))
    try:
        create_server(application, manager).run(transport="stdio")
    finally:
        if manager is not None:
            manager.close()


if __name__ == "__main__":
    main()
