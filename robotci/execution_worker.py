"""Fixed private worker entry point for the opt-in MCP simulation manager."""

from __future__ import annotations

import _thread
import argparse
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

from robotci.execution import (
    _acquire_advisory_lock,
    _managed_server_alive,
    _remove_owned_containers,
)
from robotci.runner import run_suite
from robotci.runtime_process import RuntimeProcessCancelled, set_managed_cancellation

_CANCEL = threading.Event()
_CLEANUP = threading.Event()


def _cancel(_signal: int, _frame: object) -> None:
    # Let runtime watchdog and Docker cleanup unwind cooperatively. The parent
    # still force-cleans owned groups/containers if the worker is unresponsive.
    if not _CLEANUP.is_set():
        _CANCEL.set()
        _CLEANUP.set()
        raise KeyboardInterrupt


def _watch_owner(directory: Path, stopped: threading.Event, run_id: str) -> None:
    while not stopped.wait(0.1):
        try:
            cancel = (directory / "cancel.request").exists() or not _managed_server_alive(run_id)
        except OSError:
            cancel = True
        if cancel:
            # Helpers also poll this event. Interrupt other bounded preflight
            # waits so cancellation does not wait for a full Docker build. Let
            # the main-thread handler set the event/latch first: setting the
            # event in this thread can race a helper already entering cleanup.
            if os.name == "posix":
                os.kill(os.getpid(), signal.SIGINT)
            else:
                _thread.interrupt_main()
            return


def _record_exit(directory: Path, run_id: str, code: int, error: str | None) -> None:
    payload = {
        "run_id": run_id,
        "worker_pid": os.getpid(),
        "exit_code": code,
        "finished_at": time.time(),
        "cleanup_error": error,
    }
    staged = directory / ".worker.json.tmp"
    staged.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    staged.replace(directory / "worker.json")
    # Parent validation alone can publish COMPLETED. If the owning server died,
    # retained state must not remain RUNNING or claim a PASS from partial output.
    metadata = json.loads((directory / "run.json").read_text(encoding="utf-8"))
    if metadata.get("run_id") != run_id:
        raise ValueError("managed run metadata identity changed")
    metadata.update(
        {
            "state": "CANCELLED" if code == 130 and error is None else "FAILED",
            "suite_status": None,
            "suite_path": None,
            "finished_at": payload["finished_at"],
            "exit_code": code,
            "error": error
            or ("worker cancelled" if code == 130 else "awaiting owning server validation"),
        }
    )
    staged = directory / ".worker-run.json.tmp"
    staged.write_text(json.dumps(metadata, allow_nan=False, indent=2) + "\n", encoding="utf-8")
    staged.replace(directory / "run.json")


def main() -> int:
    parser = argparse.ArgumentParser(description="Internal RobotCI managed simulation worker")
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--runtime", choices=("native", "docker"), required=True)
    args = parser.parse_args()
    run_id = os.environ.get("ROBOTCI_MANAGED_RUN_ID", "")
    expected = args.project_root / ".robotci" / "runs" / run_id / "artifacts" / "suite-result.json"
    if not re.fullmatch(r"[a-f0-9]{32}", run_id) or args.output.resolve() != expected.resolve():
        print("RobotCI managed runtime error: invalid owned worker output", file=sys.stderr)
        return 3
    directory = expected.parent.parent
    stopped = threading.Event()
    lease = _acquire_advisory_lock("robotci-managed-worker")
    watcher = threading.Thread(target=_watch_owner, args=(directory, stopped, run_id), daemon=True)
    set_managed_cancellation(_CANCEL)
    signal.signal(signal.SIGTERM, _cancel)
    signal.signal(signal.SIGINT, _cancel)
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, _cancel)
    code = 3
    aborted = False
    cleanup_error = None
    try:
        watcher.start()
        code, _, _ = run_suite(
            project_root=args.project_root,
            config_path=args.config,
            output=args.output,
            runtime=args.runtime,
        )
    except (KeyboardInterrupt, RuntimeProcessCancelled):
        aborted, code = True, 130
    except (OSError, ValueError, RuntimeError) as exc:
        aborted = True
        print(f"RobotCI managed runtime error: {exc}", file=sys.stderr)
    finally:
        _CLEANUP.set()
        stopped.set()
        if args.runtime == "docker":
            try:
                _remove_owned_containers(run_id)
            except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
                cleanup_error = str(exc)
                code, aborted = 3, True
        if _CANCEL.is_set():
            code, aborted = 130 if cleanup_error is None else 3, True
        if aborted:
            shutil.rmtree(expected.parent, ignore_errors=True)
        try:
            _record_exit(directory, run_id, code, cleanup_error)
        finally:
            lease.close()
    return code


if __name__ == "__main__":
    raise SystemExit(main())
