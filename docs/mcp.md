# Read-only MCP integration

RobotCI exposes a local stdio MCP server backed by `RobotCIApplication`. It
inspects configuration, diagnostics, results, and baseline comparisons.

## Install and start

From the RobotCI checkout and activated Python 3.12 environment:

```powershell
python -m pip install -e ".[mcp]"
robotci-mcp
```

Configure an MCP client to launch `robotci-mcp` from the selected RobotCI project
directory. It communicates over stdio, not HTTP. The executable must be available
in the client's environment.

Project selection order:

1. `--project-root` command-line option.
2. `ROBOTCI_PROJECT_ROOT` environment variable.
3. Current working directory.

For the bundled example, launched from the RobotCI checkout:

```powershell
robotci-mcp --project-root examples/nav2-loopback
```

## Tools

| Tool | Input | Result |
| --- | --- | --- |
| `project_info` | None | Resolved paths, version, and effective configuration |
| `list_scenarios` | None | Configured navigation scenarios |
| `doctor` | None | Structured readiness diagnostics |
| `get_latest_suite` | None | Latest validated suite result |
| `get_scenario_result` | `scenario` | One scenario result from the latest suite |
| `compare_to_baseline` | `name` | Deterministic comparison with a named baseline |

These tools do not start scenarios, promote baselines, edit configuration, or
deploy robots. Application errors are returned as structured MCP errors. The
Python inspection layer remains independent of ROS imports.

Use an agent to explain existing measurements and deterministic verdicts.
Run/cancel tools and a LangGraph reference workflow are future roadmap items.
Keep persistent evidence in result artifacts, not only in a chat.
