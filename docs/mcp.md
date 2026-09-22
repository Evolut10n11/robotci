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

`get_latest_suite` and `get_scenario_result` validate the whole suite and every
referenced scenario result before returning data. The application and MCP tools
reuse those validated results. Consistent `FAIL`, `TIMEOUT`, and `INFRA_ERROR`
suites remain inspectable; `compare_to_baseline` requires current,
evidence-complete `PASS` results.

Structured suite errors from these two inspection tools include:

| Code | Meaning |
| --- | --- |
| `invalid_result` | A referenced scenario result is unreadable or fails schema validation |
| `inconsistent_result` | A result's scenario, status, or duration disagrees with its suite entry |
| `invalid_metadata` | Suite metadata is invalid, including an incorrect aggregate status |
| `missing_result_file` | A referenced scenario result is absent |

Errors include the relevant path and field when available. Treat these as input
problems, not robot regressions. Preserve the diagnostic and regenerate a
consistent completed suite before comparing it; the
[suite evidence contract](contracts.md#suite-evidence-consistency) defines the
duration tolerance and status order.

Use an agent to explain existing measurements and deterministic verdicts.
Run/cancel tools and a LangGraph reference workflow are future roadmap items.
Keep persistent evidence in result artifacts, not only in a chat.
