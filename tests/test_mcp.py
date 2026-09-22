from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import cast
from unittest.mock import Mock

import pytest
from mcp import Client, MCPError, StdioServerParameters
from mcp.types import INTERNAL_ERROR

from robotci.application import (
    ApplicationError,
    DiagnosticReport,
    RobotCIApplication,
)
from robotci.baselines import capture_baseline
from robotci.doctor import CheckResult
from robotci.mcp.serializers import (
    serialize_diagnostics,
    serialize_project_info,
    serialize_scenario,
    serialize_scenario_result,
    serialize_suite_comparison,
    serialize_suite_result,
)
from robotci.mcp.server import PROJECT_ROOT_ENV, create_server, resolve_project_root

FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "gate-suite"
EXPECTED_TOOLS = {
    "project_info",
    "list_scenarios",
    "doctor",
    "get_latest_suite",
    "get_scenario_result",
    "compare_to_baseline",
}


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _write_config(project: Path) -> Path:
    path = project / "robotci.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        """\
version: 1
runtime: docker
scenarios:
  - name: route
    map_id: nav2-loopback
    start: {x: 0.0, y: 0.0}
    goal: {x: 1.0, y: 0.0}
    timeout_sec: 30
""",
        encoding="utf-8",
    )
    return path


def _project_with_results(tmp_path: Path, fixture: str = "regression") -> Path:
    project = tmp_path / "project"
    _write_config(project)
    shutil.copytree(FIXTURE_ROOT / fixture, project / ".robotci")
    return project


def _add_baseline(project: Path, tmp_path: Path) -> None:
    source = tmp_path / "baseline-source"
    shutil.copytree(FIXTURE_ROOT / "baseline", source)
    capture_baseline(
        "known-good",
        source / "suite-result.json",
        store_root=project / ".robotci" / "baselines",
    )


def _assert_json_serializable(payload: object) -> None:
    json.dumps(payload, allow_nan=False)


def test_project_info_and_scenario_serializers_return_structured_json(tmp_path: Path) -> None:
    project = _project_with_results(tmp_path)
    application = RobotCIApplication(project_root=project)

    info = serialize_project_info(application.get_project_info())
    scenarios = [serialize_scenario(item) for item in application.list_scenarios()]

    assert info["project_root"] == str(project.resolve())
    assert info["config"] == {
        "version": 1,
        "runtime": "docker",
        "robot": {"visual_profile": "rover"},
        "scenarios": scenarios,
    }
    assert scenarios == [
        {
            "name": "route",
            "start": {"x": 0.0, "y": 0.0, "yaw": 0.0},
            "goal": {"x": 1.0, "y": 0.0, "yaw": 0.0},
            "timeout_sec": 30.0,
            "map_id": "nav2-loopback",
            "goal_tolerance_m": 0.25,
            "min_feedback_samples": 1,
        }
    ]
    _assert_json_serializable(info)
    _assert_json_serializable(scenarios)


def test_doctor_serializer_returns_structured_json() -> None:
    report = DiagnosticReport(
        (
            CheckResult("platform", True, "supported"),
            CheckResult("docker", False, "not available", blocking=False),
            CheckResult("runtime", True, "using native", value="native"),
        )
    )

    payload = serialize_diagnostics(report)

    assert payload["status"] == "PASS"
    assert payload["selected_runtime"] == "native"
    assert payload["checks"] == [
        {
            "name": "platform",
            "ok": True,
            "message": "supported",
            "blocking": True,
            "value": None,
        },
        {
            "name": "docker",
            "ok": False,
            "message": "not available",
            "blocking": False,
            "value": None,
        },
        {
            "name": "runtime",
            "ok": True,
            "message": "using native",
            "blocking": True,
            "value": "native",
        },
    ]
    _assert_json_serializable(payload)


def test_suite_scenario_and_baseline_serializers_return_structured_json(
    tmp_path: Path,
) -> None:
    project = _project_with_results(tmp_path)
    _add_baseline(project, tmp_path)
    application = RobotCIApplication(project_root=project)

    suite = serialize_suite_result(application.get_latest_suite_result())
    scenario = serialize_scenario_result(application.get_scenario_result("route"))
    comparison = serialize_suite_comparison(
        application.compare_to_baseline("known-good")
    )

    assert suite["status"] == "PASS"
    assert suite["scenarios"][0]["scenario"] == "route"  # type: ignore[index]
    assert suite["execution"]["schema_version"] == 1  # type: ignore[index]
    assert scenario["scenario"] == "route"
    assert scenario["metrics"]["path_length_m"] == 6.2  # type: ignore[index]
    assert scenario["task"]["map_id"] == "nav2-loopback"  # type: ignore[index]
    assert comparison["status"] == "REGRESSION"
    assert comparison["scenarios"][0]["report"]["findings"]  # type: ignore[index]
    _assert_json_serializable(suite)
    _assert_json_serializable(scenario)
    _assert_json_serializable(comparison)


@pytest.mark.anyio
async def test_server_exposes_only_six_thin_application_tools(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = _project_with_results(tmp_path)
    _add_baseline(project, tmp_path)
    monkeypatch.setattr(
        "robotci.application.run_doctor_checks",
        lambda *, require_ros=None: [CheckResult("runtime", True, "ready", value="docker")],
    )
    wrapped = RobotCIApplication(project_root=project)
    application = Mock(spec=RobotCIApplication, wraps=wrapped)
    server = create_server(cast(RobotCIApplication, application))

    async with Client(server, raise_exceptions=True) as client:
        tools = await client.list_tools()
        results = [
            await client.call_tool("project_info", {}),
            await client.call_tool("list_scenarios", {}),
            await client.call_tool("doctor", {}),
            await client.call_tool("get_latest_suite", {}),
            await client.call_tool("get_scenario_result", {"scenario": "route"}),
            await client.call_tool("compare_to_baseline", {"name": "known-good"}),
        ]

    assert {tool.name for tool in tools.tools} == EXPECTED_TOOLS
    assert all(not result.is_error for result in results)
    assert all(result.structured_content is not None for result in results)
    application.get_project_info.assert_called_once_with()
    application.list_scenarios.assert_called_once_with()
    application.get_diagnostics.assert_called_once_with()
    application.get_latest_suite_result.assert_called_once_with()
    application.get_scenario_result.assert_called_once_with("route")
    application.compare_to_baseline.assert_called_once_with("known-good")


@pytest.mark.anyio
async def test_application_error_metadata_survives_mcp_boundary(tmp_path: Path) -> None:
    path = (tmp_path / "suite-result.json").resolve()
    application = Mock(spec=RobotCIApplication)
    application.get_latest_suite_result.side_effect = ApplicationError(
        "suite metadata is invalid",
        code="invalid_metadata",
        path=path,
        field="scenarios[0].result_file",
    )
    server = create_server(cast(RobotCIApplication, application))

    async with Client(server, raise_exceptions=True) as client:
        with pytest.raises(MCPError) as error:
            await client.call_tool("get_latest_suite", {})

    assert error.value.error.code == INTERNAL_ERROR
    assert error.value.error.message == "suite metadata is invalid"
    assert error.value.error.data == {
        "message": "suite metadata is invalid",
        "code": "invalid_metadata",
        "path": str(path),
        "field": "scenarios[0].result_file",
    }


@pytest.mark.anyio
@pytest.mark.parametrize("corruption", ["duration", "result"])
async def test_real_inconsistent_artifacts_cannot_be_reported_as_pass_through_mcp(
    tmp_path: Path, corruption: str,
) -> None:
    project = _project_with_results(tmp_path, "pass")
    suite_path = project / ".robotci/suite-result.json"
    if corruption == "duration":
        payload = json.loads(suite_path.read_text(encoding="utf-8"))
        payload["scenarios"][0]["duration_sec"] = 999.0
        suite_path.write_text(json.dumps(payload), encoding="utf-8")
        expected_code, expected_field = "inconsistent_result", "scenarios[0].duration_sec"
    else:
        (suite_path.parent / "results/route.json").write_text("{broken", encoding="utf-8")
        expected_code, expected_field = "invalid_result", "scenarios[0].result_file"
    server = create_server(RobotCIApplication(project_root=project))

    async with Client(server, raise_exceptions=True) as client:
        for name, arguments in (
            ("get_latest_suite", {}),
            ("get_scenario_result", {"scenario": "route"}),
        ):
            with pytest.raises(MCPError) as error:
                await client.call_tool(name, arguments)
            assert error.value.error.code == INTERNAL_ERROR
            assert error.value.error.data["code"] == expected_code
            assert error.value.error.data["path"] == str(suite_path.resolve())
            assert error.value.error.data["field"] == expected_field


def test_project_root_resolution_precedence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    working = tmp_path / "working"
    environment = tmp_path / "environment"
    explicit = tmp_path / "explicit"
    working.mkdir()
    monkeypatch.chdir(working)

    assert resolve_project_root(environ={}) == working.resolve()
    assert resolve_project_root(
        environ={PROJECT_ROOT_ENV: str(environment)}
    ) == environment.resolve()
    assert resolve_project_root(
        explicit,
        environ={PROJECT_ROOT_ENV: str(environment)},
    ) == explicit.resolve()


def test_normal_robotci_import_does_not_require_mcp_dependency() -> None:
    code = """
import importlib.abc
import sys

class BlockMCP(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "mcp" or fullname.startswith("mcp."):
            raise AssertionError(f"unexpected optional MCP import: {fullname}")
        return None

sys.meta_path.insert(0, BlockMCP())
import robotci
import robotci.application
import robotci.cli
"""

    subprocess.run([sys.executable, "-c", code], check=True)


@pytest.mark.anyio
async def test_stdio_server_round_trip_has_clean_protocol(tmp_path: Path) -> None:
    project = _project_with_results(tmp_path)
    server_command = shutil.which("robotci-mcp")
    assert server_command is not None
    parameters = StdioServerParameters(
        command=server_command,
        args=["--project-root", str(project)],
        cwd=Path(__file__).parents[1],
        env={"PYTHONUNBUFFERED": "1"},
    )

    async with Client(parameters) as client:
        tools = await client.list_tools()
        result = await client.call_tool("project_info", {})

    assert {tool.name for tool in tools.tools} == EXPECTED_TOOLS
    assert result.is_error is False
    assert result.structured_content["project_root"] == str(project.resolve())


def test_mcp_console_script_is_packaged() -> None:
    import tomllib

    pyproject = Path(__file__).parents[1] / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))

    assert data["project"]["scripts"]["robotci-mcp"] == "robotci.mcp.server:main"
    assert data["project"]["optional-dependencies"]["mcp"] == ["mcp>=2.0,<3.0"]
