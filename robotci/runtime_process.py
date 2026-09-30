"""Bound runtime processes and clean up children without importing ROS.

Native Nav2 launch uses ``setsid``, so stopping only the wrapper's process group
can leave the simulator alive. On Linux, retain descendant identities while the
wrapper runs and signal their owned groups on a deadline. Process start times
prevent a recycled PID from being mistaken for a child of this run.
"""

from __future__ import annotations

import logging
import os
import signal
import subprocess
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

PROCESS_POLL_SEC = 0.5
PROCESS_TERM_GRACE_SEC = 5.0
PROCESS_KILL_WAIT_SEC = 2.0
_OWNERSHIP_VARIABLE = "ROBOTCI_PROCESS_OWNER"
_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class _ProcessIdentity:
    pid: int
    parent: int
    group: int
    started: str
    state: str


def _process_table() -> dict[int, _ProcessIdentity]:
    table: dict[int, _ProcessIdentity] = {}
    try:
        # A mounted host /proc can expose a different PID namespace. Never
        # adopt those unrelated host processes using a container-local PID.
        if int(Path("/proc/self/stat").read_text().split(" ", 1)[0]) != os.getpid():
            return table
        entries = Path("/proc").iterdir()
        for entry in entries:
            if not entry.name.isdecimal():
                continue
            try:
                # The command name can itself contain spaces or ')'.
                fields = (entry / "stat").read_text().rsplit(")", 1)[1].split()
                pid = int(entry.name)
                table[pid] = _ProcessIdentity(
                    pid=pid,
                    parent=int(fields[1]),
                    group=int(fields[2]),
                    started=fields[19],
                    state=fields[0],
                )
            except (OSError, ValueError, IndexError):
                continue  # Process exit and reparenting race with the snapshot.
    except (OSError, ValueError):
        pass
    return table


def _remember_descendants(
    root: int,
    known: dict[int, _ProcessIdentity],
    table: dict[int, _ProcessIdentity],
    *, allow_root: bool = True,
) -> None:
    parents = {
        pid for pid, identity in known.items()
        if pid in table and table[pid].started == identity.started
    }
    # Do not adopt the children of a new process that recycled the wrapper PID.
    if root in table and (
        (root not in known and allow_root)
        or (root in known and table[root].started == known[root].started)
    ):
        parents.add(root)
    while True:
        children = {
            pid for pid, identity in table.items()
            if identity.parent in parents and pid not in parents
        }
        if not children:
            break
        parents.update(children)
    for pid in parents:
        if pid in table and (pid not in known or table[pid].started == known[pid].started):
            known.setdefault(pid, table[pid])


def _remember_tagged_processes(
    known: dict[int, _ProcessIdentity],
    table: dict[int, _ProcessIdentity],
    ownership: str,
) -> None:
    # A setsid leader can exit between ancestry snapshots. Its orphaned children
    # still inherit this unguessable marker; identify them without adopting any
    # unrelated process that happened to acquire an old PID or process group.
    marker = f"{_OWNERSHIP_VARIABLE}={ownership}".encode()
    for pid, identity in table.items():
        try:
            environment = (Path("/proc") / str(pid) / "environ").read_bytes().split(b"\0")
        except OSError:
            continue
        if marker in environment:
            known[pid] = identity


def _signal_owned_processes(
    root: int,
    known: dict[int, _ProcessIdentity],
    sig: int,
    *, root_alive: bool,
    ownership: str,
) -> None:
    table = _process_table()
    _remember_descendants(root, known, table, allow_root=root_alive)
    _remember_tagged_processes(known, table, ownership)
    groups: set[int] = set()
    # While Popen still owns an unreaped child, its PID cannot be recycled. This
    # is also the safe fallback when /proc is unavailable or another namespace.
    if root_alive and (
        root not in table or root not in known or table[root].started == known[root].started
    ):
        groups.add(root)
    individuals: set[int] = set()
    for pid, identity in known.items():
        current = table.get(pid)
        if current is None or current.started != identity.started or current.state == "Z":
            continue
        if current.group == identity.group:
            groups.add(current.group)
        else:
            individuals.add(pid)
    for group in groups:
        try:
            os.killpg(group, sig)
        except ProcessLookupError:
            pass
        except OSError as exc:
            _LOGGER.warning("Cannot signal runtime process group %s: %s", group, exc)
    for pid in individuals:
        try:
            os.kill(pid, sig)
        except ProcessLookupError:
            pass
        except OSError as exc:
            _LOGGER.warning("Cannot signal runtime process %s: %s", pid, exc)


def _owned_processes_alive(root: int, known: dict[int, _ProcessIdentity]) -> bool:
    table = _process_table()
    _remember_descendants(root, known, table, allow_root=False)
    return any(
        pid in table
        and table[pid].started == identity.started
        and table[pid].state != "Z"
        for pid, identity in known.items()
    )


def _stop_process(
    process: subprocess.Popen[bytes],
    known: dict[int, _ProcessIdentity],
    ownership: str,
) -> None:
    if os.name == "posix":
        _signal_owned_processes(
            process.pid, known, signal.SIGTERM,
            root_alive=process.poll() is None, ownership=ownership,
        )
        grace_deadline = time.monotonic() + PROCESS_TERM_GRACE_SEC
        while time.monotonic() < grace_deadline:
            if process.poll() is not None and not _owned_processes_alive(process.pid, known):
                break
            time.sleep(0.05)
        _signal_owned_processes(
            process.pid, known, signal.SIGKILL,
            root_alive=process.poll() is None, ownership=ownership,
        )
        if process.poll() is None:
            # PID namespaces can hide the child from /proc / killpg. Popen
            # still owns its unreaped child and can terminate it directly.
            process.kill()
    else:
        # A Windows Docker CLI can have helper children. Killing that tree is
        # separate from deleting the named container in runner._run_docker.
        if process.poll() is None:
            try:
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    capture_output=True,
                    timeout=PROCESS_TERM_GRACE_SEC,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired):
                process.kill()
            if process.poll() is None:
                process.kill()
    try:
        process.wait(timeout=PROCESS_KILL_WAIT_SEC)
    except subprocess.TimeoutExpired:
        # Never replace an expired runtime with another unbounded wait.
        pass


def run_runtime_process(
    command: list[str],
    *,
    cwd: Path,
    timeout: float,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[bytes]:
    """Run with inherited output, raising TimeoutExpired after bounded cleanup.

    The caller supplies a validated runtime budget. Forced cleanup adds at most
    5 s for termination and 2 s for reaping (Windows tree termination uses the
    same bounds). Runtime-owned Docker container cleanup belongs to the caller.
    """
    options: dict[str, object] = {"start_new_session": True} if os.name == "posix" else {
        "creationflags": subprocess.CREATE_NEW_PROCESS_GROUP,
    }
    ownership = uuid.uuid4().hex
    environment = dict(os.environ if env is None else env)
    environment[_OWNERSHIP_VARIABLE] = ownership
    process = subprocess.Popen(command, cwd=cwd, env=environment, **options)
    deadline = time.monotonic() + timeout
    known: dict[int, _ProcessIdentity] = {}
    try:
        while True:
            if os.name == "posix":
                _remember_descendants(process.pid, known, _process_table())
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(command, timeout)
            try:
                returncode = process.wait(timeout=min(PROCESS_POLL_SEC, remaining))
            except subprocess.TimeoutExpired:
                continue
            # Keep this check outside the wait exception handler: wait has
            # reaped the child, so another ancestry poll could see a reused PID.
            if time.monotonic() >= deadline:
                raise subprocess.TimeoutExpired(command, timeout)
            return subprocess.CompletedProcess(command, returncode)
    except BaseException:
        try:
            _stop_process(process, known, ownership)
        except OSError as cleanup_exc:
            _LOGGER.warning("Cannot finish runtime process cleanup: %s", cleanup_exc)
        raise
