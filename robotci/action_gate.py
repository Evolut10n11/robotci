"""Publish only reports produced by the current GitHub Action invocation."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Mapping
from pathlib import Path, PurePosixPath, PureWindowsPath

_REPORTS = (
    ("report", "ROBOTCI_REPORT", "--output", "report.json"),
    ("summary", "ROBOTCI_SUMMARY", "--markdown-output", "summary.md"),
    ("junit", "ROBOTCI_JUNIT", "--junit-output", "junit.xml"),
)
_THRESHOLDS = (
    ("ROBOTCI_MAX_DURATION", "--max-duration-increase-pct"),
    ("ROBOTCI_MAX_PATH", "--max-path-length-increase-pct"),
    ("ROBOTCI_MAX_DISTANCE", "--max-distance-to-goal-increase-m"),
    ("ROBOTCI_MAX_STUCK", "--max-stuck-events-increase"),
    ("ROBOTCI_MAX_RECOVERIES", "--max-recoveries-increase"),
)


def _declared_evidence(suite: Path) -> tuple[Path, ...]:
    """Protect declared inputs even when a result or the other suite is invalid."""
    try:
        payload = json.loads(suite.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return ()
    if not isinstance(payload, dict) or not isinstance(payload.get("scenarios"), list):
        return ()
    root = suite.parent.resolve()
    protected: list[Path] = []
    for entry in payload["scenarios"]:
        if not isinstance(entry, dict):
            continue
        reference = entry.get("result_file")
        if not isinstance(reference, str) or not reference:
            continue
        native = Path(reference)
        posix = PurePosixPath(reference)
        windows = PureWindowsPath(reference)
        if (
            not native.name
            or native.is_absolute()
            or posix.is_absolute()
            or windows.anchor
            or ".." in posix.parts
            or ".." in windows.parts
        ):
            continue
        result = (root / native).resolve()
        if result.is_relative_to(root):
            protected.extend((result, result.with_suffix(".replay.json").resolve()))
    return tuple(protected)


def _report_destinations(environment: Mapping[str, str]) -> tuple[Path, ...]:
    inputs = tuple(
        Path(environment[name]).resolve()
        for name in ("ROBOTCI_BASELINE", "ROBOTCI_CANDIDATE")
    )
    result_roots = tuple((path.parent / "results").resolve() for path in inputs)
    protected_files = list(inputs)
    for suite in inputs:
        protected_files.extend(_declared_evidence(suite))
    for root in result_roots:
        if root.is_dir():
            protected_files.extend(path for path in root.rglob("*") if path.is_file())

    destinations: list[Path] = []
    for _, name, _, _ in _REPORTS:
        value = environment[name]
        if not value or "\n" in value or "\r" in value:
            raise ValueError("report destinations must be non-empty single-line paths")
        requested = Path(value)
        if requested.is_symlink():
            raise ValueError(f"report destination must not be a symlink: {requested}")
        path = requested.resolve()
        if path in protected_files or any(path.is_relative_to(root) for root in result_roots):
            raise ValueError(f"report destination overlaps suite evidence: {requested}")
        if path.exists():
            if not path.is_file():
                raise ValueError(f"report destination must be a regular file: {requested}")
            if any(item.exists() and path.samefile(item) for item in protected_files):
                raise ValueError(f"report destination aliases suite evidence: {requested}")
        destinations.append(path)
    if len(set(destinations)) != len(destinations):
        raise ValueError("JSON, Markdown, and JUnit report destinations must be distinct")
    return tuple(destinations)


def run_action_gate(environment: Mapping[str, str]) -> int:
    """Keep invalid invocations from exposing a previous PASS as current evidence."""
    destinations: tuple[Path, ...] | None = None
    try:
        destinations = _report_destinations(environment)
        # Validate every destination before removing any old report. Suite inputs,
        # result/replay trees, and filesystem aliases must remain untouched.
        for path in destinations:
            path.unlink(missing_ok=True)
        with tempfile.TemporaryDirectory(prefix="robotci-action-") as temporary:
            stage = Path(temporary)
            command = [
                sys.executable,
                "-I",
                "-m",
                "robotci.suite_cli",
                "--baseline",
                environment["ROBOTCI_BASELINE"],
                "--candidate",
                environment["ROBOTCI_CANDIDATE"],
            ]
            for _, _, flag, filename in _REPORTS:
                command.extend((flag, str(stage / filename)))
            for name, flag in _THRESHOLDS:
                command.extend((flag, environment[name]))
            status = subprocess.run(command, check=False).returncode
            if status not in (0, 4):
                return 3
            if not all((stage / filename).is_file() for _, _, _, filename in _REPORTS):
                raise ValueError("suite gate did not produce all current reports")
            for (_, _, _, filename), destination in zip(_REPORTS, destinations, strict=True):
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(stage / filename, destination)

            summary = environment.get("GITHUB_STEP_SUMMARY")
            if summary:
                with Path(summary).open("a", encoding="utf-8") as stream:
                    stream.write((stage / "summary.md").read_text(encoding="utf-8"))
            # Publish paths last: a failed job-summary write must not advertise
            # reports which the error handler subsequently removes.
            output = environment.get("GITHUB_OUTPUT")
            if output:
                with Path(output).open("a", encoding="utf-8") as stream:
                    for name, variable, _, _ in _REPORTS:
                        stream.write(f"{name}={environment[variable]}\n")
            return status
    except (OSError, ValueError, KeyError, RuntimeError) as exc:
        print(f"RobotCI action report error: {exc}", file=sys.stderr)
        # A write failure must not leave partially published reports available to
        # unconditional uploads. Failed safety checks never reach this cleanup.
        if destinations is not None:
            for path in destinations:
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass
        return 3


def main() -> int:
    return run_action_gate(os.environ)


if __name__ == "__main__":
    raise SystemExit(main())
