from __future__ import annotations

import os
import sys
import sysconfig
import tempfile
import time
from pathlib import Path
from typing import NoReturn

_LOADER_INJECTION_VARIABLES = ("LD_AUDIT", "LD_PRELOAD")


def _controlled_python_path() -> str:
    package_parent = str(Path(__file__).resolve().parent.parent)
    install_paths = sysconfig.get_paths()
    candidates = (
        package_parent,
        install_paths.get("purelib", ""),
        install_paths.get("platlib", ""),
    )
    return os.pathsep.join(dict.fromkeys(path for path in candidates if path))


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
        os.execve(
            sys.executable,
            [
                sys.executable,
                "-S",
                "-B",
                "-P",
                "-m",
                "robotci.entrypoint",
                *sys.argv[1:],
            ],
            environment,
        )
    except OSError as exc:
        print(
            f"RobotCI runtime error: cannot start isolated CLI: {exc}",
            file=sys.stderr,
        )
        raise SystemExit(3) from exc
    raise RuntimeError("isolated CLI process unexpectedly returned")


if __name__ == "__main__":
    main()
