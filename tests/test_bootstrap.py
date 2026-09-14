from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from robotci import bootstrap


class _ExecCalled(Exception):
    pass


def test_entrypoint_relaunches_with_isolated_python(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_execve(
        executable: str,
        command: list[str],
        environment: dict[str, str],
    ) -> None:
        captured.update(
            executable=executable,
            command=command,
            environment=environment,
        )
        raise _ExecCalled

    monkeypatch.setenv("PYTHONPATH", "/untrusted/python")
    monkeypatch.setenv("PYTHONHOME", "/untrusted/home")
    monkeypatch.setenv("PYTHONWARNINGS", "error")
    monkeypatch.setattr(sys, "argv", ["robotci", "run", "--runtime", "native"])
    monkeypatch.setattr(sys, "executable", "/trusted/python")
    monkeypatch.setattr(bootstrap.sysconfig, "get_paths", lambda: {
        "purelib": "/trusted/site",
        "platlib": "/trusted/site",
    })
    monkeypatch.setattr(bootstrap.os, "getpid", lambda: 123)
    monkeypatch.setattr(bootstrap.time, "monotonic_ns", lambda: 456)
    monkeypatch.setattr(bootstrap.os, "execve", fake_execve)

    with pytest.raises(_ExecCalled):
        bootstrap.main()

    assert captured["executable"] == "/trusted/python"
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
    assert environment["PYTHONPATH"] == (
        expected_root + os.pathsep + "/trusted/site"
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

    def fake_execve(*args: object) -> None:
        nonlocal called
        called = True

    monkeypatch.setenv("LD_PRELOAD", "/untrusted/inject.so")
    monkeypatch.setattr(bootstrap.os, "execve", fake_execve)

    with pytest.raises(SystemExit) as exc_info:
        bootstrap.main()

    assert exc_info.value.code == 3
    assert not called
    assert "loader injection is unsupported" in capsys.readouterr().err
