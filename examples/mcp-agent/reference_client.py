"""Model-agnostic reference workflow; RobotCI itself decides every verdict.

Run from a checkout with the optional MCP dependency installed. Execution needs
an explicit --run flag and a prepared simulation runtime. No baseline is changed.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

from mcp import Client, StdioServerParameters


async def call(client: Client, name: str, arguments: dict, *, timeout: float = 10) -> dict:
    result = await asyncio.wait_for(
        client.call_tool(name, arguments, read_timeout_seconds=timeout),
        timeout=timeout,
    )
    if result.structured_content is None:
        raise ValueError(f"{name} returned no structured evidence")
    return result.structured_content


async def cancel_and_wait(client: Client, run_id: str) -> None:
    # A stdio client's teardown may force-kill its server after only two seconds.
    # Keep the connection alive until owned cleanup has actually completed.
    deadline = time.monotonic() + 40
    await call(client, "cancel_run", {"run_id": run_id}, timeout=5)
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("owned cleanup did not finish; inspect retained job diagnostics")
        run = await call(client, "get_run", {"run_id": run_id}, timeout=min(5, remaining))
        if run["state"] not in {"RUNNING", "CANCELLING"}:
            return
        await asyncio.sleep(min(0.1, remaining))


async def workflow(args: argparse.Namespace) -> int:
    arguments = [
        "-m",
        "robotci.mcp.server",
        "--project-root",
        str(args.project_root.resolve()),
        "--config",
        str(args.config),
    ]
    if args.run:
        arguments.append("--allow-execution")
    parameters = StdioServerParameters(
        command=sys.executable, args=arguments, env=dict(os.environ),
    )
    async with Client(parameters, raise_exceptions=True, read_timeout_seconds=10) as client:
        diagnostics = await call(client, "doctor", {}, timeout=120)
        print(json.dumps({"diagnostics": diagnostics}, ensure_ascii=False, indent=2))
        if not args.run:
            suite = await call(client, "get_latest_suite", {})
            comparison = await call(client, "compare_to_baseline", {"name": args.baseline})
        else:
            started = await call(client, "run_suite", {"runtime": args.runtime})
            run_id = started["run_id"]
            deadline = time.monotonic() + float(started["budget_sec"]) + 30
            try:
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        print(
                            "Managed simulation did not finish within its documented budget.",
                            file=sys.stderr,
                        )
                        return 3
                    run = await call(
                        client, "get_run", {"run_id": run_id}, timeout=min(10, remaining)
                    )
                    if run["state"] not in {"RUNNING", "CANCELLING"}:
                        break
                    await asyncio.sleep(0.5)
                if run["state"] != "COMPLETED" or run["suite_status"] != "PASS":
                    print(json.dumps({"run": run}, ensure_ascii=False, indent=2))
                    return 3 if run["state"] != "COMPLETED" else int(run["exit_code"])
                suite = run
                comparison = await call(
                    client,
                    "compare_run_to_baseline",
                    {"run_id": run_id, "name": args.baseline},
                )
            finally:
                # Idempotent for completed jobs; owned cancellation on interruption.
                await asyncio.shield(cancel_and_wait(client, run_id))
        print(json.dumps({"suite": suite, "comparison": comparison}, ensure_ascii=False, indent=2))
        return 4 if comparison["status"] == "REGRESSION" else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect or run a RobotCI simulation through MCP")
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=Path("robotci.yaml"))
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--run", action="store_true", help="Explicitly permit a simulation suite.")
    parser.add_argument("--runtime", choices=("native", "docker"), default="native")
    args = parser.parse_args()
    try:
        return asyncio.run(workflow(args))
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(f"RobotCI MCP workflow error: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
