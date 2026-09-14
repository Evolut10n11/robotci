from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from robotci import bootstrap


def test_entrypoint_relaunches_with_isolated_python(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_run(
        command: list[str],
        **kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        captured.update(
            command=command,
            environment=kwargs["env"],
            check=kwargs["check"],
        )
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setenv("PYTHONPATH", "/untrusted/python")
    monkeypatch.setenv("PYTHONHOME", "/untrusted/home")
    monkeypatch.setenv("PYTHONWARNINGS", "error")
    monkeypatch.setattr(sys, "argv", ["robotci", "run", "--runtime", "native"])
    monkeypatch.setattr(sys, "executable", "/trusted/python")
    class FakeDistribution:
        def __init__(self, root: str) -> None:
            self.root = root

        def locate_file(self, path: str) -> str:
            assert path == ""
            return self.root

    roots = {
        "robotci": "/trusted/site",
        "PyYAML": "/trusted/system",
        "rich": "/trusted/site",
        "typer": "/trusted/site",
    }
    monkeypatch.setattr(
        bootstrap,
        "distribution",
        lambda name: FakeDistribution(roots[name]),
    )
    monkeypatch.setattr(bootstrap.os, "getpid", lambda: 123)
    monkeypatch.setattr(bootstrap.time, "monotonic_ns", lambda: 456)
    monkeypatch.setattr(bootstrap.subprocess, "run", fake_run)

    with pytest.raises(SystemExit) as exc_info:
        bootstrap.main()

    assert exc_info.value.code == 0
    assert captured["check"] is False
    assert captured["command"] == [
        "/trusted/python",
        "-S",
        "-B",
        "-P",
        "-m",
        "robotci.entrypoint",
        "run",
        "--runtime",
        "native",
    ]
    environment = captured["environment"]
    assert isinstance(environment, dict)
    expected_root = str(Path(bootstrap.__file__).resolve().parent.parent)
    assert environment["PYTHONPATH"] == os.pathsep.join(
        (
            expected_root,
            str(Path("/trusted/site").resolve()),
            str(Path("/trusted/system").resolve()),
        )
    )
    assert environment["PYTHONHASHSEED"] == "0"
    assert environment["PYTHONNOUSERSITE"] == "1"
    assert environment["PYTHONDONTWRITEBYTECODE"] == "1"
    assert environment["PYTHONUTF8"] == "1"
    assert environment["PYTHONPYCACHEPREFIX"].endswith(
        "robotci-pycache-123-456"
    )
    assert "/untrusted" not in environment["PYTHONPATH"]
    assert "PYTHONHOME" not in environment
    assert "PYTHONWARNINGS" not in environment


def test_entrypoint_rejects_loader_injection_before_relaunch(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    called = False

    def fake_run(*args: object, **kwargs: object) -> None:
        nonlocal called
        called = True

    monkeypatch.setenv("LD_PRELOAD", "/untrusted/inject.so")
    monkeypatch.setattr(bootstrap.subprocess, "run", fake_run)

    with pytest.raises(SystemExit) as exc_info:
        bootstrap.main()

    assert exc_info.value.code == 3
    assert not called
    assert "loader injection is unsupported" in capsys.readouterr().err
