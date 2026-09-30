"""Bounded cleanup of processes tagged with this adapter's Gazebo partition."""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
from pathlib import Path


def _identity(pid: int) -> tuple[str, str] | None:
    try:
        fields = (Path("/proc") / str(pid) / "stat").read_text().rsplit(")", 1)[1].split()
        return fields[19], fields[0]  # Linux start time and process state
    except (OSError, ValueError, IndexError):
        return None


def _owned(partition: str) -> dict[int, tuple[str, str]]:
    # Never inspect/signal a mounted host /proc from a different PID namespace.
    if int(Path("/proc/self/stat").read_text().split(" ", 1)[0]) != os.getpid():
        raise RuntimeError("cannot verify Gazebo ownership across PID namespaces")
    marker = f"GZ_PARTITION={partition}".encode()
    # `timeout` launches this helper with the same environment. Ancestors are
    # the wrapper/cleanup controller, never simulator resources to terminate.
    ancestors = {os.getpid()}
    ancestor = os.getpid()
    while ancestor > 1:
        try:
            fields = (Path("/proc") / str(ancestor) / "stat").read_text().rsplit(")", 1)[1]
            ancestor = int(fields.split()[1])
        except (OSError, ValueError, IndexError):
            break
        ancestors.add(ancestor)
    owned = {}
    for entry in Path("/proc").iterdir():
        if not entry.name.isdecimal() or int(entry.name) in ancestors:
            continue
        identity = _identity(int(entry.name))
        if identity is None or identity[1] == "Z":
            continue
        try:
            if marker in (entry / "environ").read_bytes().split(b"\0"):
                owned[int(entry.name)] = identity
        except OSError:
            continue  # exiting/reparenting processes race with a snapshot
    return owned


def _signal(owned: dict[int, tuple[str, str]], sig: int) -> None:
    for pid, (started, _) in owned.items():
        identity = _identity(pid)
        if identity is None or identity[0] != started or identity[1] == "Z":
            continue  # never signal a recycled PID or a reaped process
        try:
            os.kill(pid, sig)
        except ProcessLookupError:
            pass


def stop_owned_gazebo(partition: str) -> dict[str, object]:
    if not partition.startswith("robotci-robotci-gazebo."):
        raise ValueError("a per-attempt RobotCI Gazebo partition is required")
    if sys.platform != "linux":
        raise RuntimeError("Gazebo process cleanup requires Linux /proc ownership")
    seen: set[int] = set()
    for sig, grace in ((signal.SIGTERM, 5.0), (signal.SIGKILL, 2.0)):
        deadline = time.monotonic() + grace
        signaled: set[tuple[int, str]] = set()
        while True:
            owned = _owned(partition)
            seen.update(owned)
            if not owned:
                return {"process_groups_stopped": True, "owned_processes_stopped": True,
                        "processes_seen": sorted(seen), "survivors": []}
            fresh = {pid: identity for pid, identity in owned.items()
                     if (pid, identity[0]) not in signaled}
            _signal(fresh, sig)
            signaled.update((pid, identity[0]) for pid, identity in fresh.items())
            if time.monotonic() >= deadline:
                break
            time.sleep(0.05)
    survivors = sorted(_owned(partition))
    return {"process_groups_stopped": not survivors, "owned_processes_stopped": not survivors,
            "processes_seen": sorted(seen), "survivors": survivors}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    data = {
        "schema_version": 1, "kind": "gazebo_runtime", "status": "ERROR", "checks": {},
    }
    try:
        if args.output.is_file():
            parsed = json.loads(args.output.read_text(encoding="utf-8"))
            if not isinstance(parsed, dict):
                raise ValueError("readiness evidence must be a JSON object")
            data = parsed
    except (OSError, ValueError) as exc:
        # Broken evidence must never bypass physical process cleanup.
        data["error"] = f"invalid readiness evidence: {type(exc).__name__}: {exc}"
    try:
        cleanup = stop_owned_gazebo(os.environ.get("GZ_PARTITION", ""))
    except (OSError, ValueError, RuntimeError) as exc:
        cleanup = {"process_groups_stopped": False, "owned_processes_stopped": False,
                   "error": f"{type(exc).__name__}: {exc}"}
    data["cleanup"] = cleanup
    args.output.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return 0 if cleanup["process_groups_stopped"] and data.get("status") == "READY" else 3


if __name__ == "__main__":
    raise SystemExit(main())
