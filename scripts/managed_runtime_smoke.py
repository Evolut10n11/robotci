"""Run one real Loopback route through the opted-in stdio MCP job surface.

This is a runtime CI smoke, not external-team validation. Requires the source
checkout, optional MCP dependency, and a working native or Docker runtime.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from dataclasses import asdict, replace
from pathlib import Path

import yaml
from mcp import Client, StdioServerParameters

from robotci.config import load_config
from robotci.suite_schema import load_suite_result
from robotci.viewer import load_replay


async def _call(client: Client, name: str, arguments: dict, timeout: float = 10) -> dict:
    result = await asyncio.wait_for(
        client.call_tool(name, arguments, read_timeout_seconds=timeout),
        timeout=timeout,
    )
    if result.structured_content is None:
        raise ValueError(f"{name} returned no structured content")
    return result.structured_content


async def _finish_cancel(client: Client, run_id: str) -> None:
    deadline = time.monotonic() + 40
    await _call(client, "cancel_run", {"run_id": run_id})
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("managed smoke cleanup did not finish")
        run = await _call(client, "get_run", {"run_id": run_id}, min(5, remaining))
        if run["state"] not in {"RUNNING", "CANCELLING"}:
            return
        await asyncio.sleep(0.1)


async def smoke(runtime: str, output: Path) -> None:
    checkout = Path(__file__).resolve().parents[1]
    previous_path = checkout / "artifacts" / "suite-result.json"
    previous = previous_path.read_bytes() if previous_path.is_file() else None
    source = load_config(checkout / "robotci.yaml")
    config = replace(source, scenarios=(source.scenarios[0],))
    project = output.resolve() / "project"
    project.mkdir(parents=True, exist_ok=False)
    (project / "robotci.yaml").write_text(
        yaml.safe_dump(asdict(config), sort_keys=False),
        encoding="utf-8",
        newline="\n",
    )
    parameters = StdioServerParameters(
        command=sys.executable,
        args=[
            "-m",
            "robotci.mcp.server",
            "--allow-execution",
            "--project-root",
            str(project),
            "--config",
            "robotci.yaml",
            "--max-run-sec",
            "1200",
        ],
        cwd=checkout,
        env=dict(os.environ),
    )
    async with Client(parameters, raise_exceptions=True, read_timeout_seconds=10) as client:
        tools = {tool.name for tool in (await client.list_tools()).tools}
        if len(tools) != 10 or not {"run_suite", "get_run", "cancel_run"} <= tools:
            raise ValueError(f"unexpected opted-in tools: {tools}")
        started = await _call(client, "run_suite", {"runtime": runtime})
        run_id = started["run_id"]
        try:
            deadline = time.monotonic() + float(started["budget_sec"]) + 30
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("managed runtime smoke exhausted its budget")
                run = await _call(client, "get_run", {"run_id": run_id}, min(10, remaining))
                if run["state"] not in {"RUNNING", "CANCELLING"}:
                    break
                if run["suite_path"] is not None:
                    raise ValueError("running job advertised incomplete suite evidence")
                await asyncio.sleep(0.5)
            print(json.dumps(run, indent=2))
            if run["state"] != "COMPLETED" or run["suite_status"] != "PASS":
                raise ValueError(f"managed {runtime} navigation did not PASS: {run}")
            suite = load_suite_result(Path(run["suite_path"]))
            if suite.runtime != runtime or len(suite.scenarios) != 1:
                raise ValueError("managed suite runtime/scenario count disagrees")
            result = suite.scenarios[0].result
            if not result.evidence_complete or not result.provenance_complete:
                raise ValueError("managed navigation lacks complete evidence/provenance")
            replay_path = suite.scenarios[0].result_path.with_suffix(".replay.json")
            replay = load_replay(replay_path)
            if replay["result_status"] != "PASS" or not replay["samples"]:
                raise ValueError("managed replay lacks observed successful navigation")
            if (project / ".robotci" / "suite-result.json").exists():
                raise ValueError("managed job overwrote the project's latest suite path")
            if previous is not None and previous_path.read_bytes() != previous:
                raise ValueError("managed job changed the ordinary CLI suite evidence")
            print(f"Managed {runtime} stdio MCP navigation + observed replay PASS")
        finally:
            await asyncio.shield(_finish_cancel(client, run_id))


def main() -> int:
    parser = argparse.ArgumentParser(description="Real managed RobotCI runtime smoke")
    parser.add_argument("--runtime", choices=("native", "docker"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        asyncio.run(smoke(args.runtime, args.output))
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(f"Managed runtime smoke failed: {exc}", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
