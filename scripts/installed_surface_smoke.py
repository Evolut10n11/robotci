"""Exercise public entry points from an installed wheel, outside the checkout.

Run with the clean environment's ``python -I``. The checkout supplies only the
example configuration; it must never supply imported Python or viewer assets.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from html.parser import HTMLParser
from importlib.metadata import distribution
from pathlib import Path
from typing import BinaryIO
from urllib.parse import urljoin, urlsplit
from urllib.request import urlopen

EXPECTED_TOOLS = {
    "project_info",
    "list_scenarios",
    "doctor",
    "get_latest_suite",
    "get_scenario_result",
    "compare_to_baseline",
}
COMMAND_TIMEOUT_SEC = 20
VIEWER_STARTUP_TIMEOUT_SEC = 20
MCP_TIMEOUT_SEC = 30
MAX_HTTP_BYTES = 8 * 1024 * 1024


class SmokeError(RuntimeError):
    pass


class _Assets(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.paths: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        path = values.get("src") if tag == "script" else None
        if tag == "link" and values.get("rel") == "stylesheet":
            path = values.get("href")
        if path:
            self.paths.append(path)


def _check(condition: bool, message: str) -> None:
    if not condition:
        raise SmokeError(message)


def _installed_command(name: str) -> str:
    suffix = ".exe" if os.name == "nt" else ""
    folder = "Scripts" if os.name == "nt" else "bin"
    command = Path(sys.prefix) / folder / (name + suffix)
    _check(command.is_file(), f"installed entry point is missing: {name}")
    return str(command)


def _verify_install(checkout: Path) -> None:
    _check(bool(sys.flags.isolated), "invoke the smoke script with python -I")
    import robotci

    prefix = Path(sys.prefix).resolve()
    package = Path(robotci.__file__).resolve()
    _check(sys.prefix != sys.base_prefix, "use a clean virtual environment")
    _check(package.is_relative_to(prefix), "RobotCI was imported outside the virtual environment")
    _check(not package.is_relative_to(checkout), "RobotCI was imported from the checkout")
    metadata = distribution("robotci")
    direct_url = metadata.read_text("direct_url.json")
    if direct_url:
        _check(
            not json.loads(direct_url).get("dir_info", {}).get("editable", False),
            "the smoke environment contains an editable RobotCI install",
        )
    print(f"Installed package: {package}")


def _environment() -> dict[str, str]:
    env = {name: value for name, value in os.environ.items() if not name.startswith("PYTHON")}
    env.update({"PYTHONNOUSERSITE": "1", "PYTHONUNBUFFERED": "1", "NO_COLOR": "1"})
    return env


def _cli_smoke(project: Path, env: dict[str, str]) -> None:
    robotci = _installed_command("robotci")
    commands = [
        [robotci, "version"],
        [robotci, "validate", "--config", "robotci.yaml"],
        [robotci, "plan", "--config", "robotci.yaml"],
        [_installed_command("robotci-init"), "--help"],
        [_installed_command("robotci-baseline"), "--help"],
        [_installed_command("robotci-support-bundle"), "--help"],
    ]
    for index, command in enumerate(commands):
        result = subprocess.run(
            command,
            cwd=project,
            env=env,
            capture_output=True,
            text=True,
            timeout=COMMAND_TIMEOUT_SEC,
            check=True,
        )
        if index == 0:
            _check(result.stdout.strip() == "RobotCI 0.1.0a1", "unexpected packaged version")
    print("Installed CLI/version/validate/plan/entry points: PASS")


def _read_lines(stream: BinaryIO, lines: queue.Queue[bytes | None]) -> None:
    try:
        for line in stream:
            lines.put(line)
    finally:
        lines.put(None)


def _stop_child(process: subprocess.Popen[bytes]) -> None:
    # These surfaces do not launch robot runtimes. The Windows CLI bootstrap
    # delegates to a child interpreter, so clean that owned tree too. Never use
    # process-name searches or PID enumeration in a packaging smoke.
    if process.poll() is None:
        if os.name == "nt":
            try:
                result = subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    capture_output=True,
                    timeout=5,
                    check=False,
                )
                _check(result.returncode == 0, "owned Windows viewer tree cleanup failed")
            except (OSError, subprocess.TimeoutExpired, SmokeError) as exc:
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=5)
                raise SmokeError("could not confirm owned Windows viewer tree cleanup") from exc
        else:
            process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def _get(url: str) -> bytes:
    with urlopen(url, timeout=3) as response:
        _check(response.status == 200, f"HTTP request failed: {url}")
        content = response.read(MAX_HTTP_BYTES + 1)
    _check(0 < len(content) <= MAX_HTTP_BYTES, f"empty or oversized HTTP response: {url}")
    return content


def _viewer_smoke(project: Path, env: dict[str, str]) -> None:
    lines: queue.Queue[bytes | None] = queue.Queue()
    with tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(
            [_installed_command("robotci"), "view", "--demo", "--no-open", "--port", "0"],
            cwd=project,
            env=env,
            stdout=subprocess.PIPE,
            stderr=errors,
        )
        assert process.stdout is not None
        reader = threading.Thread(target=_read_lines, args=(process.stdout, lines), daemon=True)
        reader.start()
        try:
            deadline = time.monotonic() + VIEWER_STARTUP_TIMEOUT_SEC
            url = None
            while url is None:
                remaining = deadline - time.monotonic()
                _check(remaining > 0, "installed viewer did not become ready before its deadline")
                try:
                    line = lines.get(timeout=remaining)
                except queue.Empty as exc:
                    raise SmokeError("installed viewer startup timed out") from exc
                _check(line is not None, "installed viewer exited before becoming ready")
                match = re.search(rb"Viewer: (http://127\.0\.0\.1:\d+/)", line)
                if match:
                    url = match[1].decode("ascii")
            _check(json.loads(_get(urljoin(url, "healthz"))) == {"status": "ok"}, "bad healthz")
            session = json.loads(_get(urljoin(url, "api/session")))
            _check(session["schema_version"] == 1, "unexpected viewer session schema")
            _check(session["source"] == "demo" and session["gate"] is None, "invalid demo session")
            _check(session["selected_scenario"] == "deterministic_demo", "wrong demo scenario")
            replay = json.loads(_get(urljoin(url, "api/replay")))
            _check(replay["scenario"] == "deterministic_demo", "wrong demo replay")
            html = _get(url).decode("utf-8")
            _check('id="root"' in html, "installed viewer HTML is missing its root")
            assets = _Assets()
            assets.feed(html)
            _check(len(assets.paths) >= 2, "installed viewer is missing script or stylesheet links")
            for path in assets.paths:
                asset_url = urljoin(url, path)
                _check(urlsplit(asset_url).netloc == urlsplit(url).netloc, "nonlocal viewer asset")
                _get(asset_url)
        finally:
            _stop_child(process)
            reader.join(timeout=2)
            process.stdout.close()
    print("Installed viewer/demo/session/replay/HTML/static assets: PASS")


async def _mcp_smoke(project: Path, env: dict[str, str]) -> None:
    from mcp import Client, StdioServerParameters

    parameters = StdioServerParameters(
        command=_installed_command("robotci-mcp"),
        args=["--project-root", str(project)],
        cwd=project,
        env=env,
    )
    # The SDK owns and closes the stdio server process on success or cancellation.
    async with asyncio.timeout(MCP_TIMEOUT_SEC):
        async with Client(parameters, read_timeout_seconds=10) as client:
            tools = await client.list_tools()
            _check(
                {tool.name for tool in tools.tools} == EXPECTED_TOOLS,
                "default MCP tools changed",
            )
            info = await client.call_tool("project_info", {})
            _check(not info.is_error, "installed MCP project_info failed")
            _check(
                info.structured_content["project_root"] == str(project.resolve()),
                "installed MCP used a different project root",
            )
            scenarios = await client.call_tool("list_scenarios", {})
            _check(not scenarios.is_error, "installed MCP list_scenarios failed")
            _check(len(scenarios.structured_content["scenarios"]) == 3, "wrong MCP scenario count")
    print("Installed MCP/stdio/default six tools/project info/scenarios: PASS")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkout-root", required=True, type=Path)
    args = parser.parse_args()
    checkout = args.checkout_root.resolve()
    with tempfile.TemporaryDirectory(prefix="robotci-installed-smoke-") as temporary:
        project = Path(temporary) / "project"
        shutil.copytree(checkout / "examples" / "nav2-loopback", project)
        os.chdir(project)
        _check(not project.is_relative_to(checkout), "smoke directory must be outside the checkout")
        _verify_install(checkout)
        env = _environment()
        _cli_smoke(project, env)
        _viewer_smoke(project, env)
        asyncio.run(_mcp_smoke(project, env))


if __name__ == "__main__":
    main()
