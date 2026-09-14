from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path
from typing import NoReturn

_LOADER_INJECTION_VARIABLES = ("LD_AUDIT", "LD_PRELOAD")
_REPLACE_PROCESS = os.name != "nt"
_PYTHON_DISTRIBUTIONS = ("robotci", "PyYAML", "rich", "typer")


def _controlled_python_path() -> str:
    roots = [str(Path(__file__).resolve().parent.parent)]
    for name in _PYTHON_DISTRIBUTIONS:
        try:
            package = distribution(name)
        except PackageNotFoundError as exc:
            raise RuntimeError(
                f"Python distribution metadata is unavailable for {name}"
            ) from exc
        root = str(Path(package.locate_file("")).resolve())
        if root not in roots:
            roots.append(root)
    return os.pathsep.join(roots)


def _isolated_environment() -> dict[str, str]:
    environment = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith("PYTHON")
    }
    cache_prefix = (
        Path(tempfile.gettempdir())
        / f"robotci-pycache-{os.getpid()}-{time.monotonic_ns()}"
    )
    python_path = _controlled_python_path()
    if not python_path:
        raise RuntimeError("Python dependency paths are unavailable")
    environment.update(
        {
            "PYTHONHASHSEED": "0",
            "PYTHONNOUSERSITE": "1",
            "PYTHONPATH": python_path,
            "PYTHONPYCACHEPREFIX": str(cache_prefix),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONUTF8": "1",
        }
    )
    return environment


def main() -> NoReturn:
    """Relaunch the CLI before importing application or runtime modules."""

    injected = [
        name for name in _LOADER_INJECTION_VARIABLES if os.environ.get(name)
    ]
    if injected:
        print(
            "RobotCI runtime error: loader injection is unsupported: "
            + ", ".join(injected),
            file=sys.stderr,
        )
        raise SystemExit(3)

    try:
        environment = _isolated_environment()
        command = [
            sys.executable,
            "-S",
            "-B",
            "-P",
            "-m",
            "robotci.entrypoint",
            *sys.argv[1:],
        ]
        if _REPLACE_PROCESS:
            os.execve(sys.executable, command, environment)
            raise RuntimeError("isolated CLI process unexpectedly returned")
        completed = subprocess.run(
            command,
            env=environment,
            check=False,
        )
    except OSError as exc:
        print(
            f"RobotCI runtime error: cannot start isolated CLI: {exc}",
            file=sys.stderr,
        )
        raise SystemExit(3) from exc
    raise SystemExit(completed.returncode)


if __name__ == "__main__":
    main()
