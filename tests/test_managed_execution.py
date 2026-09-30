from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import asdict
from pathlib import Path

import pytest
from mcp import Client, MCPError, StdioServerParameters

from robotci.application import RobotCIApplication
from robotci.baselines import capture_baseline
from robotci.execution import (
    ExecutionError,
    ExecutionManager,
    _acquire_runtime_lock,
    _managed_server_alive,
    _remove_owned_containers,
)
from robotci.mcp.server import create_server, main
from robotci.reproducibility import (
    build_suite_execution_identity,
    build_suite_plan_fingerprint,
    inherited_runtime_environment,
)
from robotci.runtime_process import (
    RuntimeProcessCancelled,
    docker_container_name,
    run_runtime_process,
)
from robotci.suite_schema import load_suite_result

FIXTURE = Path(__file__).parent / "fixtures" / "gate-suite" / "pass"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _application(project: Path) -> RobotCIApplication:
    project.mkdir(parents=True, exist_ok=True)
    (project / "robotci.yaml").write_text(
        "version: 1\nruntime: native\nscenarios:\n"
        "  - name: route\n    map_id: nav2-loopback\n"
        "    start: {x: 0, y: 0}\n    goal: {x: 1, y: 0}\n"
        "    timeout_sec: 30\n",
        encoding="utf-8",
    )
    return RobotCIApplication(project_root=project)


def _write_completed(command: list[str], runtime: str = "native") -> Path:
    from robotci.config import load_config

    output = Path(command[command.index("--output") + 1])
    config = load_config(command[command.index("--config") + 1])
    shutil.copytree(FIXTURE, output.parent, dirs_exist_ok=True)
    original = load_suite_result(output)
    identity = build_suite_execution_identity(
        runtime=runtime,
        plan_fingerprint=build_suite_plan_fingerprint(config, timeout_sec=None),
        environment=original.execution.environment,
    )
    payload = json.loads(output.read_text())
    payload["runtime"] = runtime
    payload["execution"] = asdict(identity)
    output.write_text(json.dumps(payload), encoding="utf-8")
    return output


def _terminal(manager: ExecutionManager, run_id: str) -> dict[str, object]:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        result = manager.get(run_id)
        if result["state"] not in {"RUNNING", "CANCELLING"}:
            return result
        time.sleep(0.01)
    pytest.fail("managed job did not finish")


def _success(command, **kwargs):
    assert kwargs["stdin"] == subprocess.DEVNULL
    _write_completed(command)
    return subprocess.CompletedProcess(command, 0)


def test_completed_run_retains_isolated_evidence_and_original_latest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application = _application(tmp_path)
    shutil.copytree(FIXTURE, tmp_path / ".robotci", dirs_exist_ok=True)
    latest = tmp_path / ".robotci" / "suite-result.json"
    previous = latest.read_bytes()
    monkeypatch.setattr("robotci.execution.run_runtime_process", _success)
    manager = ExecutionManager(application)
    try:
        initial = manager.start(runtime="native")
        completed = _terminal(manager, initial["run_id"])
        assert completed["state"] == "COMPLETED"
        assert completed["suite_status"] == "PASS"
        assert completed["exit_code"] == 0
        assert latest.read_bytes() == previous
        assert Path(completed["suite_path"]).parent != latest.parent
        assert re.fullmatch(r"[0-9a-f]{32}", initial["run_id"])
        assert manager.cancel(initial["run_id"])["state"] == "COMPLETED"
        metadata = json.loads((Path(completed["directory"]) / "run.json").read_text())
        assert metadata == completed
    finally:
        manager.close()


def test_no_partial_evidence_while_running_and_concurrent_servers_refused(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ready = threading.Event()
    release = threading.Event()

    def blocking(command, **kwargs):
        _write_completed(command)
        ready.set()
        release.wait(timeout=5)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr("robotci.execution.run_runtime_process", blocking)
    first = ExecutionManager(_application(tmp_path / "first"))
    second = ExecutionManager(_application(tmp_path / "second"))
    try:
        started = first.start(runtime="native")
        assert ready.wait(timeout=3)
        assert first.get(started["run_id"])["suite_path"] is None
        with pytest.raises(ExecutionError, match="already active"):
            first.start(runtime="native")
        with pytest.raises(ExecutionError) as busy:
            second.start(runtime="native")
        assert busy.value.code == "runtime_busy"
        with pytest.raises(ExecutionError) as incomplete:
            first.compare(started["run_id"], "known-good")
        assert incomplete.value.code == "run_incomplete"
        release.set()
        assert _terminal(first, started["run_id"])["state"] == "COMPLETED"
    finally:
        release.set()
        first.close()
        second.close()


def test_configuration_is_snapshotted_before_worker_runs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entered = threading.Event()
    release = threading.Event()

    def blocking(command, **kwargs):
        entered.set()
        release.wait(timeout=5)
        return _success(command, **kwargs)

    application = _application(tmp_path)
    monkeypatch.setattr("robotci.execution.run_runtime_process", blocking)
    manager = ExecutionManager(application)
    try:
        started = manager.start(runtime="native")
        assert entered.wait(timeout=3)
        application.context.config_path.write_text("broken new config", encoding="utf-8")
        release.set()
        assert _terminal(manager, started["run_id"])["state"] == "COMPLETED"
    finally:
        release.set()
        manager.close()


@pytest.mark.parametrize("corruption", ["exit", "plan", "snapshot", "task"])
def test_inconsistent_or_tampered_completed_results_are_not_published(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    corruption: str,
) -> None:
    def invalid(command, **kwargs):
        output = _write_completed(command)
        if corruption == "plan":
            # A valid but foreign-plan suite must be rejected as this job's evidence.
            shutil.copy2(FIXTURE / "suite-result.json", output)
        if corruption == "snapshot":
            Path(command[command.index("--config") + 1]).write_text("changed")
        if corruption == "task":
            result = output.parent / "results" / "route.json"
            payload = json.loads(result.read_text())
            payload["start"]["x"] = 8
            result.write_text(json.dumps(payload))
        return subprocess.CompletedProcess(command, 3 if corruption == "exit" else 0)

    monkeypatch.setattr("robotci.execution.run_runtime_process", invalid)
    manager = ExecutionManager(_application(tmp_path))
    try:
        run = manager.start(runtime="native")
        terminal = _terminal(manager, run["run_id"])
        assert terminal["state"] == "FAILED"
        assert terminal["suite_path"] is None
        assert not (Path(terminal["directory"]) / "artifacts").exists()
        assert terminal["error"]
    finally:
        manager.close()


@pytest.mark.parametrize("terminal", ["cancel", "timeout"])
def test_cancel_or_timeout_removes_partial_pass(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    terminal: str,
) -> None:
    ready = threading.Event()

    def interrupted(command, **kwargs):
        _write_completed(command)
        ready.set()
        if terminal == "cancel":
            assert kwargs["cancel_event"].wait(timeout=3)
            raise RuntimeProcessCancelled("cancel")
        raise subprocess.TimeoutExpired(command, 1)

    monkeypatch.setattr("robotci.execution.run_runtime_process", interrupted)
    manager = ExecutionManager(_application(tmp_path))
    try:
        run = manager.start(runtime="native")
        assert ready.wait(timeout=3)
        if terminal == "cancel":
            assert manager.cancel(run["run_id"])["state"] == "CANCELLING"
        result = _terminal(manager, run["run_id"])
        assert result["state"] == ("CANCELLED" if terminal == "cancel" else "TIMED_OUT")
        assert result["suite_status"] is None
        assert result["suite_path"] is None
        assert not (Path(result["directory"]) / "artifacts").exists()
    finally:
        manager.close()


def test_close_cancels_owned_job_and_releases_runtime_lock(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def wait_for_cancel(command, **kwargs):
        assert kwargs["cancel_event"].wait(timeout=3)
        raise RuntimeProcessCancelled("server closed")

    monkeypatch.setattr("robotci.execution.run_runtime_process", wait_for_cancel)
    manager = ExecutionManager(_application(tmp_path))
    run = manager.start(runtime="native")
    manager.close()
    manager.close()
    assert manager.get(run["run_id"])["state"] == "CANCELLED"
    with pytest.raises(ExecutionError) as error:
        manager.start(runtime="native")
    assert error.value.code == "manager_closed"
    # A new server can start after cleanup; no PID-based stale lock recovery.
    another = ExecutionManager(_application(tmp_path))
    another.start(runtime="native")
    another.close()


@pytest.mark.parametrize("run_id", ["../suite-result.json", "123", "f" * 32])
def test_unknown_or_foreign_job_refused(tmp_path: Path, run_id: str) -> None:
    manager = ExecutionManager(_application(tmp_path))
    for operation in (manager.get, manager.cancel):
        with pytest.raises(ExecutionError) as error:
            operation(run_id)
        assert error.value.code == "unknown_run"
    manager.close()


def test_configuration_budget_refused_before_any_process_or_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "robotci.execution.run_runtime_process", lambda *a, **k: pytest.fail("no process")
    )
    manager = ExecutionManager(_application(tmp_path), max_run_sec=1)
    with pytest.raises(ExecutionError) as error:
        manager.start(runtime="native")
    assert error.value.code == "budget_exceeded"
    assert not (tmp_path / ".robotci" / "runs").exists()
    with pytest.raises(ExecutionError) as error:
        manager.start(runtime="auto")
    assert error.value.code == "invalid_runtime"


def test_owned_completed_run_uses_existing_deterministic_baseline_gate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("robotci.execution.run_runtime_process", _success)
    manager = ExecutionManager(_application(tmp_path))
    try:
        run = manager.start(runtime="native")
        result = _terminal(manager, run["run_id"])
        store = tmp_path / ".robotci" / "baselines"
        capture_baseline("known-good", Path(result["suite_path"]), store_root=store)
        assert manager.compare(run["run_id"], "known-good")["status"] == "PASS"
        assert list(store.iterdir()) == [store / "known-good"]
    finally:
        manager.close()


def test_owned_docker_cleanup_never_removes_other_names(monkeypatch: pytest.MonkeyPatch) -> None:
    owner = "a" * 32
    own = f"robotci-run-{owner}-{'b' * 32}"
    probe = f"robotci-env-{owner}-{'c' * 32}"
    commands = []

    def run(command, **kwargs):
        commands.append(command)
        if "ps" in command:
            names = f"{own}\n{probe}\nrobotci-run-{'f' * 32}\n{own}-extra\nother\n"
            return subprocess.CompletedProcess(command, 0, stdout=names)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr("robotci.execution.subprocess.run", run)
    _remove_owned_containers(owner)
    assert commands[1] == ["docker", "rm", "--force", own, probe]


def test_managed_container_names_are_unique_and_not_execution_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = "a" * 32
    monkeypatch.setenv("ROBOTCI_MANAGED_RUN_ID", owner)
    monkeypatch.setenv("ROBOTCI_MANAGED_PROCESS_OWNER", "b" * 32)
    first, second = docker_container_name("run"), docker_container_name("run")
    assert first != second
    assert re.fullmatch(rf"robotci-run-{owner}-[a-f0-9]{{32}}", first)
    assert "ROBOTCI_MANAGED_RUN_ID" not in inherited_runtime_environment()
    assert "ROBOTCI_MANAGED_PROCESS_OWNER" not in inherited_runtime_environment()


def test_real_process_cancellation_is_bounded_and_output_is_redirected(tmp_path: Path) -> None:
    cancel = threading.Event()
    errors = []

    def worker():
        try:
            with (tmp_path / "log").open("wb") as log:
                run_runtime_process(
                    [
                        sys.executable,
                        "-c",
                        "import time; print('owned output', flush=True); time.sleep(30)",
                    ],
                    cwd=tmp_path,
                    timeout=60,
                    cancel_event=cancel,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                )
        except RuntimeProcessCancelled:
            errors.append("cancelled")

    thread = threading.Thread(target=worker)
    thread.start()
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        if (tmp_path / "log").exists() and "owned output" in (tmp_path / "log").read_text():
            break
        time.sleep(0.01)
    cancel.set()
    thread.join(timeout=10)
    assert not thread.is_alive()
    assert errors == ["cancelled"]
    assert (tmp_path / "log").read_text() == "owned output\n"


def test_docker_cancellation_cleans_exact_owned_names_and_cannot_keep_partial_pass(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ready = threading.Event()
    cleaned = []

    def interrupted(command, **kwargs):
        _write_completed(command, runtime="docker")
        ready.set()
        assert kwargs["cancel_event"].wait(timeout=3)
        raise RuntimeProcessCancelled("cancel")

    monkeypatch.setattr("robotci.execution.run_runtime_process", interrupted)
    monkeypatch.setattr("robotci.execution._remove_owned_containers", cleaned.append)
    manager = ExecutionManager(_application(tmp_path))
    try:
        run = manager.start(runtime="docker")
        assert ready.wait(timeout=3)
        manager.cancel(run["run_id"])
        result = _terminal(manager, run["run_id"])
        assert result["state"] == "CANCELLED"
        assert result["suite_path"] is None
        assert cleaned == [run["run_id"]]
    finally:
        manager.close()


def test_cleanup_failure_is_visible_and_never_a_completed_pass(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def success(command, **kwargs):
        _write_completed(command, runtime="docker")
        return subprocess.CompletedProcess(command, 0)

    def failure(run_id):
        raise ExecutionError("daemon did not respond", code="cleanup_failed")

    monkeypatch.setattr("robotci.execution.run_runtime_process", success)
    monkeypatch.setattr("robotci.execution._remove_owned_containers", failure)
    manager = ExecutionManager(_application(tmp_path))
    try:
        run = manager.start(runtime="docker")
        result = _terminal(manager, run["run_id"])
        assert result["state"] == "FAILED"
        assert result["suite_status"] is None
        assert result["suite_path"] is None
        assert "cleanup" in result["error"]
    finally:
        manager.close()


@pytest.mark.skipif(
    Path("/opt/ros/jazzy/setup.bash").is_file(),
    reason="missing-runtime smoke requires no ROS",
)
def test_actual_fixed_worker_reports_missing_runtime_without_polluting_protocol(
    tmp_path: Path,
) -> None:
    manager = ExecutionManager(_application(tmp_path))
    try:
        run = manager.start(runtime="native")
        result = _terminal(manager, run["run_id"])
        assert result["state"] == "FAILED"
        assert result["suite_path"] is None
        log = Path(result["log_path"]).read_text()
        assert "RobotCI managed runtime error:" in log
        assert result["exit_code"] == 3
    finally:
        manager.close()


@pytest.mark.parametrize("budget", [True, -1, 0, float("nan"), float("inf"), 10**1000])
def test_server_rejects_invalid_budget(tmp_path: Path, budget) -> None:
    with pytest.raises(ExecutionError) as error:
        ExecutionManager(_application(tmp_path), max_run_sec=budget)
    assert error.value.code == "invalid_budget"


@pytest.mark.anyio
async def test_opted_in_mcp_tools_keep_status_responsive_and_shutdown_cancels(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def wait_for_cancel(command, **kwargs):
        assert kwargs["cancel_event"].wait(timeout=5)
        raise RuntimeProcessCancelled("server closed")

    monkeypatch.setattr("robotci.execution.run_runtime_process", wait_for_cancel)
    application = _application(tmp_path)
    manager = ExecutionManager(application)
    server = create_server(application, manager)
    async with Client(server, raise_exceptions=True) as client:
        tools = {tool.name: tool for tool in (await client.list_tools()).tools}
        assert len(tools) == 10
        assert tools["run_suite"].annotations.read_only_hint is False
        assert tools["get_run"].annotations.read_only_hint is True
        run = (await client.call_tool("run_suite", {"runtime": "native"})).structured_content
        started = time.monotonic()
        status = (await client.call_tool("get_run", {"run_id": run["run_id"]})).structured_content
        assert status["state"] == "RUNNING"
        assert time.monotonic() - started < 1
        with pytest.raises(MCPError) as error:
            await client.call_tool("cancel_run", {"run_id": "f" * 32})
        assert error.value.error.data["code"] == "unknown_run"
        with pytest.raises(MCPError) as error:
            await client.call_tool("run_suite", {"runtime": "native"})
        assert error.value.error.data["code"] == "runtime_busy"
    assert manager.get(run["run_id"])["state"] == "CANCELLED"


@pytest.mark.parametrize(
    "arguments",
    [["--allow-execution"], ["--allow-execution", "--project-root", "."]],
)
def test_mcp_execution_requires_explicit_project_and_config(arguments, capsys) -> None:
    with pytest.raises(SystemExit) as error:
        main(arguments)
    assert error.value.code == 2
    assert "requires explicit --project-root and --config" in capsys.readouterr().err


@pytest.mark.anyio
async def test_opted_in_stdio_tool_errors_preserve_clean_protocol(tmp_path: Path) -> None:
    application = _application(tmp_path)
    parameters = StdioServerParameters(
        command=sys.executable,
        args=[
            "-m",
            "robotci.mcp.server",
            "--project-root",
            str(tmp_path),
            "--config",
            str(application.context.config_path),
            "--allow-execution",
            "--max-run-sec",
            "1",
        ],
        env={"PYTHONPATH": str(Path(__file__).parents[1])},
    )
    async with Client(parameters, raise_exceptions=True) as client:
        assert len((await client.list_tools()).tools) == 10
        with pytest.raises(MCPError) as error:
            await client.call_tool("run_suite", {"runtime": "native"})
        assert error.value.error.data["code"] == "budget_exceeded"
        info = (await client.call_tool("project_info", {})).structured_content
        assert info["project_root"] == str(tmp_path)


@pytest.mark.anyio
async def test_missing_baseline_is_a_structured_input_error(tmp_path: Path) -> None:
    server = create_server(_application(tmp_path))
    async with Client(server, raise_exceptions=True) as client:
        with pytest.raises(MCPError) as error:
            await client.call_tool("compare_to_baseline", {"name": "absent"})
        assert error.value.error.data["code"] == "invalid_input"
        assert "baseline" in error.value.error.message


def test_managed_docker_probe_cancellation_removes_its_exact_owned_container(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from robotci import reproducibility, runtime_process

    owner = "a" * 32
    monkeypatch.setenv("ROBOTCI_MANAGED_RUN_ID", owner)
    monkeypatch.setattr(reproducibility, "_docker_compose_fingerprint", lambda path: "fixed")
    started = []

    def interrupted(command, **kwargs):
        started.append(command)
        raise RuntimeProcessCancelled("worker cancel")

    removed = []

    def cleanup(command, **kwargs):
        removed.append(command)
        return subprocess.CompletedProcess(command, 0, stderr="")

    monkeypatch.setattr(runtime_process, "run_runtime_process", interrupted)
    monkeypatch.setattr(reproducibility.subprocess, "run", cleanup)
    with pytest.raises(RuntimeProcessCancelled):
        reproducibility._collect_docker_environment(tmp_path)
    name = started[0][started[0].index("--name") + 1]
    assert re.fullmatch(rf"robotci-env-{owner}-[a-f0-9]{{32}}", name)
    assert removed == [["docker", "rm", "--force", name]]


def test_managed_docker_probe_malformed_output_remains_strict_and_diagnostic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from robotci import reproducibility, runtime_process

    monkeypatch.setenv("ROBOTCI_MANAGED_RUN_ID", "a" * 32)
    monkeypatch.setattr(reproducibility, "_docker_compose_fingerprint", lambda path: "fixed")

    def noisy(command, **kwargs):
        kwargs["stdout"].write(b"unexpected build progress\n" + b"x" * 2048)
        kwargs["stderr"].write(b"diagnostic\n" + b"y" * 2048)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(runtime_process, "run_runtime_process", noisy)
    with pytest.raises(reproducibility.ReproducibilityError) as error:
        reproducibility._collect_docker_environment(tmp_path, build_image=True)
    message = str(error.value)
    assert "invalid environment metadata" in message
    assert "unexpected build progress" in message
    assert "diagnostic" in message
    assert len(message) < 1000


def test_owned_runtime_stdin_can_be_detached_from_the_mcp_protocol(tmp_path: Path) -> None:
    with (tmp_path / "log").open("wb") as log:
        completed = run_runtime_process(
            [sys.executable, "-c", "import sys; print(repr(sys.stdin.buffer.read()), flush=True)"],
            cwd=tmp_path, timeout=5, stdin=subprocess.DEVNULL, stdout=log,
        )
    assert completed.returncode == 0
    assert (tmp_path / "log").read_text().strip() == "b''"


def test_parent_reservation_identity_rejects_a_different_server() -> None:
    lock = _acquire_runtime_lock()
    owner = Path(tempfile.gettempdir()) / "robotci-managed-runtime.owner"
    try:
        owner.write_text("a" * 32, encoding="ascii")
        assert _managed_server_alive("a" * 32)
        assert not _managed_server_alive("b" * 32)
    finally:
        lock.close()
    assert not _managed_server_alive("a" * 32)


def test_inner_watchdog_does_not_adopt_its_managed_worker_parent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from robotci import runtime_process

    captured = []

    class Child:
        pid = 100

        def wait(self, timeout):
            raise subprocess.TimeoutExpired("child", timeout)

    def popen(command, **kwargs):
        captured.append(kwargs["env"])
        return Child()

    monkeypatch.setenv("ROBOTCI_MANAGED_PROCESS_OWNER", "a" * 32)
    monkeypatch.setattr(runtime_process.subprocess, "Popen", popen)
    monkeypatch.setattr(runtime_process, "_process_table", lambda: {})
    times = iter([0, 0.1, 2])
    monkeypatch.setattr(runtime_process.time, "monotonic", lambda: next(times))
    stopped = []
    monkeypatch.setattr(
        runtime_process, "_stop_process",
        lambda process, known, owner: stopped.append(owner),
    )
    with pytest.raises(subprocess.TimeoutExpired):
        run_runtime_process(["fixed child"], cwd=tmp_path, timeout=1)
    assert captured[0]["ROBOTCI_MANAGED_PROCESS_OWNER"] == "a" * 32
    assert captured[0]["ROBOTCI_PROCESS_OWNER"] != "a" * 32
    assert stopped == [captured[0]["ROBOTCI_PROCESS_OWNER"]]


@pytest.mark.anyio
@pytest.mark.skipif(os.name != "posix", reason="POSIX stdio process-group teardown")
async def test_sdk_forced_stdio_shutdown_retains_worker_cleanup_lock_and_terminal_state(
    tmp_path: Path,
) -> None:
    import asyncio

    _application(tmp_path)
    # Exercise the real private worker and cancellation/lock protocol, with a
    # harmless owned subprocess instead of ROS. Five-second unwind exceeds the
    # stdio SDK's two-second server shutdown grace period.
    injected = r'''
import time
from pathlib import Path
from robotci.runtime_process import run_runtime_process
import robotci.runner
def simulated_suite(**arguments):
    directory = Path(arguments["output"]).parent.parent
    heartbeat = directory / "heartbeat"
    child = (
        "import pathlib,time\np=pathlib.Path(" + repr(str(heartbeat)) + ")\n"
        "while True:\n p.write_text(str(time.monotonic()))\n time.sleep(0.02)\n"
    )
    try:
        run_runtime_process([sys.executable, "-c", child], cwd=directory, timeout=60)
    finally:
        time.sleep(5)
robotci.runner.run_suite = simulated_suite
'''
    server_code = (
        "import robotci.execution as execution\n"
        f"injected = {injected!r}\n"
        "execution._ISOLATED_LAUNCHER = execution._ISOLATED_LAUNCHER.replace("
        "'runpy.run_module', injected + '\\nrunpy.run_module', 1)\n"
        "from robotci.mcp.server import main\n"
        f"main(['--project-root', {str(tmp_path)!r}, "
        "'--config', 'robotci.yaml', '--allow-execution'])\n"
    )
    parameters = StdioServerParameters(
        command=sys.executable, args=["-c", server_code],
        env={"PYTHONPATH": str(Path(__file__).parents[1])},
    )
    async with Client(parameters, raise_exceptions=True, read_timeout_seconds=10) as client:
        run = (await client.call_tool("run_suite", {"runtime": "native"})).structured_content
        directory = Path(run["directory"])
        deadline = time.monotonic() + 5
        while not (directory / "heartbeat").exists():
            assert time.monotonic() < deadline
            await asyncio.sleep(0.02)
    # The server was forcibly stopped before the worker's slow cleanup ended.
    with pytest.raises(ExecutionError) as busy:
        _acquire_runtime_lock()
    assert busy.value.code == "runtime_busy"
    deadline = time.monotonic() + 10
    while not (directory / "worker.json").exists():
        assert time.monotonic() < deadline
        await asyncio.sleep(0.02)
    metadata = json.loads((directory / "run.json").read_text())
    assert metadata["state"] == "CANCELLED"
    assert metadata["suite_path"] is None
    assert metadata["suite_status"] is None
    heartbeat = (directory / "heartbeat").read_text()
    await asyncio.sleep(0.1)
    assert (directory / "heartbeat").read_text() == heartbeat
    lock = _acquire_runtime_lock()
    lock.close()
