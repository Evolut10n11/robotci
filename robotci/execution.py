"""Opt-in, local simulation jobs with owned cancellation and retained evidence.

There is no shell/tool-supplied command surface. One server owns its job IDs;
an OS advisory lock also prevents two managed servers sharing runtime resources.
The ordinary CLI remains synchronous and must not run concurrently with jobs.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import BinaryIO, Literal

import yaml

from robotci.application import RobotCIApplication
from robotci.bootstrap import _ISOLATED_LAUNCHER, _isolated_environment
from robotci.config import RobotCIConfig, load_config
from robotci.mcp.serializers import serialize_suite_comparison
from robotci.reproducibility import build_suite_plan_fingerprint
from robotci.runner import _result_matches_task, _runtime_budget
from robotci.runtime_process import RuntimeProcessCancelled, run_runtime_process
from robotci.suite_schema import load_suite_result

ManagedRuntime = Literal["native", "docker"]
RunState = Literal["RUNNING", "CANCELLING", "COMPLETED", "CANCELLED", "TIMED_OUT", "FAILED"]
DEFAULT_MAX_RUN_SEC = 3600.0
MAX_RUNS_PER_SERVER = 128
DOCKER_CLEANUP_SEC = 15.0
_RUN_ID = re.compile(r"^[0-9a-f]{32}$")
_EXIT_BY_STATUS = {"PASS": 0, "FAIL": 1, "TIMEOUT": 2, "INFRA_ERROR": 3}


class ExecutionError(ValueError):
    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.code = code

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": str(self)}


@dataclass
class _Run:
    run_id: str
    runtime: ManagedRuntime
    directory: Path
    config: RobotCIConfig
    config_digest: str
    budget_sec: float
    started_at: float = field(default_factory=time.time)
    state: RunState = "RUNNING"
    finished_at: float | None = None
    suite_status: str | None = None
    exit_code: int | None = None
    error: str | None = None
    cancel: threading.Event = field(default_factory=threading.Event)
    thread: threading.Thread | None = None
    runtime_lock: BinaryIO | None = None

    @property
    def suite_path(self) -> Path:
        return self.directory / "artifacts" / "suite-result.json"

    def payload(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "run_id": self.run_id,
            "state": self.state,
            "runtime": self.runtime,
            "budget_sec": self.budget_sec,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "suite_status": self.suite_status,
            "exit_code": self.exit_code,
            "error": self.error,
            "config_digest": self.config_digest,
            "directory": str(self.directory),
            "log_path": str(self.directory / "runtime.log"),
            # Incomplete results are never advertised as consumable evidence.
            "suite_path": str(self.suite_path) if self.state == "COMPLETED" else None,
        }


def _acquire_advisory_lock(name: str) -> BinaryIO:
    path = Path(tempfile.gettempdir()) / f"{name}.lock"
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    stream = os.fdopen(os.open(path, flags, 0o600), "r+b")
    try:
        if os.name == "nt":
            import msvcrt

            if path.stat().st_size == 0:
                stream.write(b"0")
                stream.flush()
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (OSError, ImportError) as exc:
        stream.close()
        raise ExecutionError(
            "another managed RobotCI execution owns the runtime resources",
            code="runtime_busy",
        ) from exc
    return stream


def _acquire_runtime_lock() -> BinaryIO:
    # Parent reservation closes the startup gap. The separate worker lease
    # remains locked if a client forcibly terminates the server during cleanup.
    server = _acquire_advisory_lock("robotci-managed-runtime")
    try:
        worker = _acquire_advisory_lock("robotci-managed-worker")
        worker.close()
    except BaseException:
        server.close()
        raise
    return server


def _managed_server_alive(run_id: str) -> bool:
    try:
        probe = _acquire_advisory_lock("robotci-managed-runtime")
    except ExecutionError:
        owner = Path(tempfile.gettempdir()) / "robotci-managed-runtime.owner"
        return owner.read_text(encoding="ascii") == run_id
    probe.close()
    return False


def _remove_owned_containers(run_id: str) -> None:
    """Only names containing this job's random ID may be removed, on all OSes."""
    deadline = time.monotonic() + DOCKER_CLEANUP_SEC
    result = subprocess.run(
        [
            "docker",
            "ps",
            "-a",
            "--format",
            "{{.Names}}",
            "--filter",
            f"name=robotci-run-{run_id}-",
            "--filter",
            f"name=robotci-env-{run_id}-",
        ],
        capture_output=True,
        text=True,
        timeout=DOCKER_CLEANUP_SEC,
        check=False,
    )
    if result.returncode != 0:
        raise ExecutionError("cannot inspect owned Docker containers", code="cleanup_failed")
    pattern = re.compile(rf"^robotci-(?:run|env)-{run_id}-[0-9a-f]{{32}}$")
    names = [name for name in result.stdout.splitlines() if pattern.fullmatch(name)]
    if not names:
        return
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise ExecutionError("Docker cleanup deadline expired", code="cleanup_failed")
    cleanup = subprocess.run(
        ["docker", "rm", "--force", *names],
        capture_output=True,
        text=True,
        timeout=remaining,
        check=False,
    )
    if cleanup.returncode != 0:
        raise ExecutionError("owned Docker container cleanup failed", code="cleanup_failed")


class ExecutionManager:
    """Manage bounded simulation jobs for one explicitly selected project."""

    def __init__(
        self,
        application: RobotCIApplication,
        *,
        max_run_sec: float = DEFAULT_MAX_RUN_SEC,
    ) -> None:
        if (
            isinstance(max_run_sec, bool)
            or not isinstance(max_run_sec, (float, int))
            or not 0 < max_run_sec <= 86400
            or not math.isfinite(max_run_sec)
        ):
            raise ExecutionError("max-run-sec must be finite in (0, 86400]", code="invalid_budget")
        self.application = application
        self.max_run_sec = float(max_run_sec)
        self._runs: dict[str, _Run] = {}
        self._mutex = threading.RLock()
        self._closed = False

    def start(self, *, runtime: ManagedRuntime) -> dict[str, object]:
        if runtime not in {"native", "docker"}:
            raise ExecutionError("select native or docker explicitly", code="invalid_runtime")
        with self._mutex:
            if self._closed:
                raise ExecutionError("execution manager is closed", code="manager_closed")
            if any(run.state in {"RUNNING", "CANCELLING"} for run in self._runs.values()):
                raise ExecutionError("a simulation job is already active", code="runtime_busy")
            if len(self._runs) >= MAX_RUNS_PER_SERVER:
                raise ExecutionError(
                    "server run limit reached; restart after completion", code="run_limit"
                )
            try:
                config = load_config(self.application.context.config_path)
                # Pre/post Docker environment probes: one 300 s build + one 60 s query.
                budget = sum(
                    _runtime_budget(scenario.timeout_sec, docker=runtime == "docker")
                    for scenario in config.scenarios
                ) + (360.0 if runtime == "docker" else 60.0)
            except (OSError, ValueError) as exc:
                raise ExecutionError(str(exc), code="invalid_config") from exc
            if budget > self.max_run_sec:
                raise ExecutionError(
                    f"suite budget {budget:g} s exceeds server limit {self.max_run_sec:g} s",
                    code="budget_exceeded",
                )
            runtime_lock = _acquire_runtime_lock()
            run_id = uuid.uuid4().hex
            directory = self.application.context.project_root / ".robotci" / "runs" / run_id
            try:
                owner = Path(tempfile.gettempdir()) / "robotci-managed-runtime.owner"
                owner.write_text(run_id, encoding="ascii")
                directory.mkdir(parents=True, exist_ok=False)
                snapshot = yaml.safe_dump(asdict(config), sort_keys=False)
                snapshot_path = directory / "config.yaml"
                snapshot_path.write_text(snapshot, encoding="utf-8", newline="\n")
                run = _Run(
                    run_id,
                    runtime,
                    directory,
                    config,
                    hashlib.sha256(snapshot.encode()).hexdigest(),
                    budget,
                    runtime_lock=runtime_lock,
                )
                self._runs[run_id] = run
                self._persist(run)
                run.thread = threading.Thread(target=self._execute, args=(run,), daemon=True)
                run.thread.start()
            except BaseException:
                self._runs.pop(run_id, None)
                runtime_lock.close()
                raise
            return run.payload()

    def get(self, run_id: str) -> dict[str, object]:
        with self._mutex:
            return self._owned(run_id).payload()

    def cancel(self, run_id: str) -> dict[str, object]:
        with self._mutex:
            run = self._owned(run_id)
            if run.state in {"RUNNING", "CANCELLING"}:
                run.state = "CANCELLING"
                run.cancel.set()
                (run.directory / "cancel.request").touch()
                self._persist(run)
            return run.payload()

    def compare(self, run_id: str, name: str) -> dict[str, object]:
        with self._mutex:
            run = self._owned(run_id)
            if run.state != "COMPLETED":
                raise ExecutionError("run has no completed suite evidence", code="run_incomplete")
            path = run.suite_path
        # Existing deterministic reader/policy remains authoritative.
        report = self.application.compare_to_baseline(name, candidate_suite_path=path)
        return serialize_suite_comparison(report)

    def close(self) -> None:
        with self._mutex:
            self._closed = True
            active = [run for run in self._runs.values() if run.state in {"RUNNING", "CANCELLING"}]
            for run in active:
                run.cancel.set()
                run.state = "CANCELLING"
                (run.directory / "cancel.request").touch()
                self._persist(run)
        for run in active:
            if run.thread is not None:
                # Poll (0.5) + process cleanup (7 POSIX / 12 Windows) +
                # Docker cleanup (15), plus IO.
                run.thread.join(timeout=30.0)
                if run.thread.is_alive():
                    raise ExecutionError(
                        "owned worker cleanup did not finish", code="cleanup_failed"
                    )

    def _owned(self, run_id: str) -> _Run:
        if not isinstance(run_id, str) or not _RUN_ID.fullmatch(run_id) or run_id not in self._runs:
            raise ExecutionError("unknown run ID for this server", code="unknown_run")
        return self._runs[run_id]

    def _persist(self, run: _Run) -> None:
        staged = run.directory / ".run.json.tmp"
        staged.write_text(
            json.dumps(run.payload(), allow_nan=False, indent=2) + "\n", encoding="utf-8"
        )
        staged.replace(run.directory / "run.json")

    def _execute(self, run: _Run) -> None:
        state: RunState = "FAILED"
        suite_status = None
        error = None
        exit_code = None
        try:
            environment = _isolated_environment()
            environment["ROBOTCI_MANAGED_RUN_ID"] = run.run_id
            environment["ROBOTCI_MANAGED_PROCESS_OWNER"] = uuid.uuid4().hex
            launcher = _ISOLATED_LAUNCHER.replace("robotci.entrypoint", "robotci.execution_worker")
            command = [
                sys.executable,
                "-S",
                "-B",
                "-P",
                "-c",
                launcher,
                "--project-root",
                str(self.application.context.project_root),
                "--config",
                str(run.directory / "config.yaml"),
                "--output",
                str(run.suite_path),
                "--runtime",
                run.runtime,
            ]
            with (run.directory / "runtime.log").open("wb") as log:
                completed = run_runtime_process(
                    command,
                    cwd=self.application.context.project_root,
                    timeout=run.budget_sec,
                    env=environment,
                    cancel_event=run.cancel,
                    stdin=subprocess.DEVNULL,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    cleanup_on_exit=True,
                    managed_cleanup=True,
                )
            exit_code = completed.returncode
            snapshot = (run.directory / "config.yaml").read_bytes()
            if hashlib.sha256(snapshot).hexdigest() != run.config_digest:
                raise ExecutionError("run configuration snapshot changed", code="config_changed")
            suite = load_suite_result(run.suite_path)
            if (
                suite.runtime != run.runtime
                or suite.execution.plan_fingerprint
                != build_suite_plan_fingerprint(
                    run.config,
                    timeout_sec=None,
                )
                or tuple(item.scenario for item in suite.scenarios)
                != tuple(item.name for item in run.config.scenarios)
                or _EXIT_BY_STATUS[suite.status] != exit_code
                or not all(
                    _result_matches_task(item.result, definition)
                    for item, definition in zip(suite.scenarios, run.config.scenarios, strict=True)
                )
            ):
                raise ExecutionError("suite contradicts this managed run", code="invalid_result")
            state, suite_status = "COMPLETED", suite.status
        except RuntimeProcessCancelled:
            state = "CANCELLED"
        except subprocess.TimeoutExpired:
            state, error = "TIMED_OUT", "managed suite exhausted its execution budget"
        except (OSError, ValueError, RuntimeError) as exc:
            error = str(exc)
        finally:
            cleanup_failed = False
            if run.runtime == "docker":
                try:
                    _remove_owned_containers(run.run_id)
                except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
                    state, suite_status = "FAILED", None
                    error = f"runtime cleanup could not be confirmed: {exc}"
                    cleanup_failed = True
            with self._mutex:
                # Cancellation racing with a just-completed process still wins.
                if run.cancel.is_set() and not cleanup_failed:
                    state, suite_status = "CANCELLED", None
                if state != "COMPLETED":
                    shutil.rmtree(run.directory / "artifacts", ignore_errors=True)
                run.state, run.suite_status = state, suite_status
                run.exit_code, run.error, run.finished_at = exit_code, error, time.time()
                try:
                    self._persist(run)
                finally:
                    if run.runtime_lock is not None:
                        run.runtime_lock.close()
                        run.runtime_lock = None
