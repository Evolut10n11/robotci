import json
from pathlib import Path

import pytest

from robotci.doctor import run_doctor_checks
from robotci.platform import PlatformInfo
from robotci.support_bundle import build_support_bundle, main


def _environment(monkeypatch, *, native: bool, docker: bool, sourced: bool = True) -> None:
    monkeypatch.setattr(
        "robotci.doctor.current_platform",
        lambda: PlatformInfo("Linux", core_supported=True, ros_runtime_supported=True),
    )
    monkeypatch.setattr("robotci.runner._native_ros_available", lambda: native)
    monkeypatch.setattr("robotci.runner._docker_available", lambda: docker)
    monkeypatch.setattr(
        "robotci.doctor.command_exists", lambda command: command == "ros2" and native and sourced
    )
    monkeypatch.setattr(
        "robotci.doctor.get_ros_package_prefix", lambda package: "/private/ros" if native else None
    )
    monkeypatch.setattr(
        "robotci.doctor.get_docker_status", lambda: (docker, "Docker diagnostic")
    )
    if native and sourced:
        monkeypatch.setenv("ROS_DISTRO", "jazzy")
    else:
        monkeypatch.delenv("ROS_DISTRO", raising=False)


def _config(tmp_path: Path, runtime: str) -> Path:
    path = tmp_path / "robotci.yaml"
    path.write_text(
        f"version: 1\nruntime: {runtime}\nscenarios:\n"
        "  - name: private_route\n"
        "    start: {x: 0, y: 0}\n"
        "    goal: {x: 1, y: 1}\n",
        encoding="utf-8",
    )
    return path


@pytest.mark.parametrize("runtime", ["auto", "native", "docker"])
@pytest.mark.parametrize(
    "native,docker", [(False, False), (False, True), (True, False), (True, True)]
)
@pytest.mark.parametrize("optional", [False, True])
def test_bundle_checks_configured_runtime_without_fallback(
    tmp_path: Path, monkeypatch, runtime: str, native: bool, docker: bool, optional: bool
) -> None:
    _environment(monkeypatch, native=native, docker=docker)
    path = _config(tmp_path, runtime)
    expected = (
        "native" if native and runtime in ("auto", "native")
        else "docker" if docker and runtime in ("auto", "docker")
        else "none"
    )

    bundle = build_support_bundle(config_path=path, require_ros=False if optional else None)

    assert bundle["config"]["runtime"] == runtime
    assert bundle["doctor"]["runtime"]["selected"] == expected
    assert bundle["doctor"]["runtime"]["ok"] is (expected != "none")
    assert bundle["status"] == ("PASS" if optional or expected != "none" else "FAIL")
    runtime_check = next(c for c in bundle["doctor"]["checks"] if c["name"] == "runtime")
    assert runtime_check["blocking"] is (not optional)
    assert "/private/ros" not in json.dumps(bundle)
    assert "private_route" not in json.dumps(bundle)


@pytest.mark.parametrize(
    "native,docker", [(False, False), (False, True), (True, False), (True, True)]
)
def test_explicit_require_ros_overrides_config_runtime(
    tmp_path: Path, monkeypatch, native: bool, docker: bool
) -> None:
    _environment(monkeypatch, native=native, docker=docker)
    bundle = build_support_bundle(config_path=_config(tmp_path, "docker"), require_ros=True)

    assert bundle["doctor"]["runtime"]["selected"] == ("native" if native else "none")
    assert bundle["status"] == ("PASS" if native else "FAIL")
    checks = {c["name"]: c for c in bundle["doctor"]["checks"]}
    assert checks["ros2"]["blocking"] is True
    assert checks["docker"]["blocking"] is False


@pytest.mark.parametrize("runtime", ["auto", "native"])
def test_native_config_uses_runner_probe_not_unsourced_parent_shell(
    tmp_path: Path, monkeypatch, runtime: str
) -> None:
    _environment(monkeypatch, native=True, docker=False, sourced=False)
    path = _config(tmp_path, runtime)

    default = build_support_bundle(config_path=path)
    strict = build_support_bundle(config_path=path, require_ros=True)

    assert default["status"] == "PASS"
    assert default["doctor"]["runtime"]["selected"] == "native"
    assert strict["status"] == "FAIL"


@pytest.mark.parametrize("runtime", ["native", "docker"])
@pytest.mark.parametrize("compact", [False, True])
def test_cli_reports_missing_configured_runtime_with_blocking_exit(
    tmp_path: Path, monkeypatch, capsys, runtime: str, compact: bool
) -> None:
    _environment(monkeypatch, native=runtime == "docker", docker=runtime == "native")
    path = _config(tmp_path, runtime)
    arguments = ["--config", str(path), "--output", "-"]
    if compact:
        arguments.append("--compact")

    code = main(arguments)
    captured = capsys.readouterr()

    assert code == 1
    assert json.loads(captured.out)["status"] == "FAIL"
    assert captured.err == ""
    if compact:
        assert captured.out.count("\n") == 1


@pytest.mark.parametrize("runtime", [None, "", "invalid", True, []])
def test_doctor_rejects_unknown_runtime_before_any_probe(monkeypatch, runtime) -> None:
    def unexpected_probe():
        pytest.fail("invalid runtime must fail before environment probing")

    monkeypatch.setattr("robotci.doctor.current_platform", unexpected_probe)
    with pytest.raises(ValueError, match="unsupported runtime"):
        run_doctor_checks(runtime=runtime)
