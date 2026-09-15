from __future__ import annotations

import argparse
import os
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from mcp import MCPError
from mcp.server import MCPServer
from mcp.types import INTERNAL_ERROR

from robotci import __version__
from robotci.application import ApplicationError, RobotCIApplication
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
    except ApplicationError as exc:
        raise MCPError(
            code=INTERNAL_ERROR,
            message=str(exc),
            data=exc.as_dict(),
        ) from None


def create_server(application: RobotCIApplication) -> MCPServer:
    """Create the read-only MCP adapter around one RobotCI application facade."""

    server = MCPServer(
        "robotci",
        description="Read-only local RobotCI project inspection",
        version=__version__,
        log_level="WARNING",
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

    return server


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the read-only RobotCI MCP server.")
    parser.add_argument(
        "--project-root",
        type=Path,
        help=f"RobotCI project root (default: ${PROJECT_ROOT_ENV} or current directory).",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = _parser().parse_args(argv)
    project_root = resolve_project_root(args.project_root)
    application = RobotCIApplication(project_root=project_root)
    create_server(application).run(transport="stdio")


if __name__ == "__main__":
    main()
