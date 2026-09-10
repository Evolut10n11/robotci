from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from robotci import runner


def test_auto_runtime_prefers_native_ros_on_linux(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runner.stdlib_platform, "system", lambda: "Linux")
    monkeypatch.setattr(runner, "_command_exists", lambda command: command == "ros2")
    monkeypatch.setattr(runner, "_docker_available", lambda: True)

    assert runner.select_runtime("auto") == "native"


def test_auto_runtime_uses_docker_on_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runner.stdlib_platform, "system", lambda: "Windows")
    monkeypatch.setattr(runner, "_docker_available", lambda: True)

    assert runner.select_runtime("auto") == "docker"


def test_auto_runtime_fails_cleanly_without_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runner.stdlib_platform, "system", lambda: "Windows")
    monkeypatch.setattr(runner, "_docker_available", lambda: False)

    with pytest.raises(runner.RuntimeUnavailableError, match="no usable runtime found"):
        runner.select_runtime("auto")


def test_native_runtime_is_rejected_on_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runner.stdlib_platform, "system", lambda: "Windows")

    with pytest.raises(runner.RuntimeUnavailableError, match="requires Linux"):
        runner.select_runtime("native")


def test_find_project_root_walks_up_from_nested_directory(tmp_path: Path) -> None:
    root = tmp_path / "robotci"
    nested = root / "some" / "nested" / "directory"
    scripts = root / "scripts"
    nested.mkdir(parents=True)
    scripts.mkdir()
    (root / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    (scripts / "run_simple_route.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")

    assert runner._find_project_root(nested) == root


def test_run_native_passes_result_and_timeout_to_script(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script = tmp_path / "scripts" / "run_simple_route.sh"
    script.parent.mkdir()
    script.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    output = tmp_path / ".robotci" / "result.json"
    captured: dict[str, object] = {}

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["command"] = command
        captured["cwd"] = kwargs["cwd"]
        captured["env"] = kwargs["env"]
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    exit_code = runner._run_native(tmp_path, output, 42.5)

    assert exit_code == 0
    assert captured["command"] == ["bash", str(script)]
    assert captured["cwd"] == tmp_path
    environment = captured["env"]
    assert isinstance(environment, dict)
    assert environment["ROBOTCI_RESULT_FILE"] == str(output.resolve())
    assert environment["ROBOTCI_TIMEOUT_SEC"] == "42.5"


def test_run_docker_copies_container_result_to_requested_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "artifacts" / "simple-route" / "result.json"
    destination = tmp_path / ".robotci" / "result.json"
    captured: dict[str, object] = {}

    def fake_run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        captured["command"] = command
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text('{"status": "PASS"}\n', encoding="utf-8")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    exit_code = runner._run_docker(tmp_path, destination, 30.0)

    assert exit_code == 0
    assert destination.read_text(encoding="utf-8") == '{"status": "PASS"}\n'
    command = captured["command"]
    assert isinstance(command, list)
    assert command[:5] == ["docker", "compose", "run", "--rm", "--build"]
    assert "ROBOTCI_TIMEOUT_SEC=30.0" in command


def test_read_result_status(tmp_path: Path) -> None:
    result_path = tmp_path / "result.json"
    result_path.write_text(json.dumps({"status": "PASS"}), encoding="utf-8")

    assert runner.read_result_status(result_path) == "PASS"
