from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from robotci import runtime_process


def _identity(
    pid: int, parent: int, group: int, started: str = "first",
) -> runtime_process._ProcessIdentity:
    return runtime_process._ProcessIdentity(pid, parent, group, started, "S")


@pytest.mark.skipif(os.name != "posix", reason="POSIX process groups")
def test_unobserved_reaped_root_cannot_adopt_a_recycled_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    known: dict[int, runtime_process._ProcessIdentity] = {}
    table = {100: _identity(100, 1, 100, "recycled"), 101: _identity(101, 100, 100)}
    monkeypatch.setattr(runtime_process, "_process_table", lambda: table)
    monkeypatch.setattr(runtime_process.Path, "read_bytes", lambda self: b"")
    monkeypatch.setattr(
        runtime_process.os, "killpg", lambda *args: pytest.fail("foreign group must survive"),
    )
    runtime_process._signal_owned_processes(
        100, known, signal.SIGTERM, root_alive=False, ownership="unique",
    )
    assert known == {}


@pytest.mark.skipif(os.name != "posix", reason="POSIX process groups")
def test_recycled_root_and_child_pids_are_not_adopted_or_signalled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    known = {100: _identity(100, 1, 100), 101: _identity(101, 100, 101)}
    table = {
        100: _identity(100, 1, 100, "recycled"),
        101: _identity(101, 1, 101, "recycled"),
        102: _identity(102, 100, 100),
    }
    monkeypatch.setattr(runtime_process, "_process_table", lambda: table)
    monkeypatch.setattr(runtime_process.Path, "read_bytes", lambda self: b"OTHER=value\0")
    groups: list[int] = []
    individuals: list[int] = []
    monkeypatch.setattr(runtime_process.os, "killpg", lambda group, sig: groups.append(group))
    monkeypatch.setattr(runtime_process.os, "kill", lambda pid, sig: individuals.append(pid))
    runtime_process._signal_owned_processes(
        100, known, signal.SIGTERM, root_alive=False, ownership="unique",
    )
    assert known[100].started == "first"
    assert known[101].started == "first"
    assert 102 not in known
    assert groups == []
    assert individuals == []


@pytest.mark.skipif(os.name != "posix", reason="POSIX process groups")
def test_reparented_owned_member_preserves_detached_group_ownership(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    known = {100: _identity(100, 1, 100), 101: _identity(101, 100, 101),
             102: _identity(102, 101, 101)}
    table = {102: _identity(102, 1, 101)}
    monkeypatch.setattr(runtime_process, "_process_table", lambda: table)
    monkeypatch.setattr(runtime_process.Path, "read_bytes", lambda self: b"")
    groups: list[int] = []
    monkeypatch.setattr(runtime_process.os, "killpg", lambda group, sig: groups.append(group))
    runtime_process._signal_owned_processes(
        100, known, signal.SIGKILL, root_alive=False, ownership="unique",
    )
    assert groups == [101]


@pytest.mark.skipif(os.name != "posix", reason="POSIX process groups")
def test_ownership_marker_recovers_orphan_missed_by_ancestry_poll(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    known = {100: _identity(100, 1, 100)}
    table = {102: _identity(102, 1, 101), 999: _identity(999, 1, 999)}
    monkeypatch.setattr(runtime_process, "_process_table", lambda: table)

    def read_environment(path: Path) -> bytes:
        return b"ROBOTCI_PROCESS_OWNER=unique\0" if path.parts[-2] == "102" else b""

    monkeypatch.setattr(runtime_process.Path, "read_bytes", read_environment)
    groups: list[int] = []
    monkeypatch.setattr(runtime_process.os, "killpg", lambda group, sig: groups.append(group))
    runtime_process._signal_owned_processes(
        100, known, signal.SIGKILL, root_alive=False, ownership="unique",
    )
    assert groups == [101]
    assert 999 not in known


def test_mismatched_proc_pid_namespace_is_never_enumerated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(runtime_process.os, "getpid", lambda: 100)
    monkeypatch.setattr(runtime_process.Path, "read_text", lambda self: "200 (other) S 1 200")
    monkeypatch.setattr(
        runtime_process.Path, "iterdir", lambda self: pytest.fail("must not inspect host /proc"),
    )
    assert runtime_process._process_table() == {}


def test_wrapper_completion_after_deadline_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    class LateProcess:
        pid = 100

        def wait(self, timeout):
            return 0

    times = iter([0.0, 0.1, 1.1, 1.2])
    monkeypatch.setattr(runtime_process.subprocess, "Popen", lambda *args, **kwargs: LateProcess())
    monkeypatch.setattr(runtime_process.time, "monotonic", lambda: next(times))
    monkeypatch.setattr(runtime_process, "_process_table", lambda: {})
    stopped: list[int] = []
    monkeypatch.setattr(
        runtime_process, "_stop_process", lambda process, known, tag: stopped.append(1),
    )
    with pytest.raises(subprocess.TimeoutExpired):
        runtime_process.run_runtime_process(["runtime"], cwd=tmp_path, timeout=1.0)
    assert stopped == [1]


def test_windows_cleanup_does_not_address_reaped_process_by_recycled_pid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ReapedProcess:
        pid = 100

        def poll(self):
            return 0

        def wait(self, timeout):
            return 0

        def kill(self):
            pytest.fail("reaped child must not be addressed by PID")

    monkeypatch.setattr(runtime_process, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(
        runtime_process.subprocess, "run", lambda *args, **kwargs: pytest.fail("no taskkill"),
    )
    runtime_process._stop_process(ReapedProcess(), {}, "unique")


def test_process_success_and_hang_are_bounded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(runtime_process, "PROCESS_TERM_GRACE_SEC", 0.1)
    completed = runtime_process.run_runtime_process(
        [sys.executable, "-c", "raise SystemExit(2)"], cwd=tmp_path, timeout=5.0,
    )
    assert completed.returncode == 2  # Navigation TIMEOUT exit remains unchanged.
    started = time.monotonic()
    with pytest.raises(subprocess.TimeoutExpired):
        runtime_process.run_runtime_process(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            cwd=tmp_path, timeout=0.1,
        )
    assert time.monotonic() - started < 3.0


_MATCHING_PROC_NAMESPACE = os.name == "posix" and os.getpid() in runtime_process._process_table()


@pytest.mark.skipif(
    not _MATCHING_PROC_NAMESPACE, reason="matching Linux /proc PID namespace required",
)
@pytest.mark.parametrize("orphan_leader", [False, True])
def test_timeout_stops_detached_child_after_its_leader_exits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, orphan_leader: bool,
) -> None:
    heartbeat = tmp_path / "heartbeat"
    child = tmp_path / "child.py"
    child.write_text(
        "import pathlib, signal, time\n"
        "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        f"path = pathlib.Path({str(heartbeat)!r})\n"
        "while True:\n    path.write_text(str(time.monotonic()))\n    time.sleep(0.02)\n",
        encoding="utf-8",
    )
    parent = tmp_path / "parent.py"
    if orphan_leader:
        launch = (
            "import subprocess, sys; "
            f"subprocess.Popen([sys.executable, {str(child)!r}])"
        )
        spawn = f"subprocess.Popen([sys.executable, '-c', {launch!r}], start_new_session=True)"
    else:
        spawn = f"subprocess.Popen([sys.executable, {str(child)!r}], start_new_session=True)"
    parent.write_text(
        f"import subprocess, sys, time\n{spawn}\ntime.sleep(30)\n", encoding="utf-8",
    )
    monkeypatch.setattr(runtime_process, "PROCESS_TERM_GRACE_SEC", 0.2)
    with pytest.raises(subprocess.TimeoutExpired):
        runtime_process.run_runtime_process(
            [sys.executable, str(parent)], cwd=tmp_path, timeout=1.0,
        )
    before = heartbeat.read_text()
    time.sleep(0.2)
    assert heartbeat.read_text() == before
