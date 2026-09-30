# MCP inspection and managed simulation

RobotCI exposes a local stdio MCP server backed by `RobotCIApplication`. It
inspects configuration, diagnostics, results, and baseline comparisons. The
default server exposes only six read-only tools. Managed simulation execution
requires an explicit command-line opt-in.

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

## Default inspection tools

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

## Enable managed simulation jobs

Start only against a prepared, trusted simulation project. Both project and
config must be selected explicitly; environment variables never enable execution:

```powershell
robotci-mcp --allow-execution --project-root examples/nav2-loopback --config robotci.yaml
```

`--config` is relative to the selected project root unless absolute. Linux native
execution requires the existing ROS2 Jazzy/Nav2 setup. Windows can inspect and
manage Docker jobs when a Linux-container Docker backend is available; installing
MCP does not install ROS or Docker. Runtime assets still require the source checkout.

The opted-in server exposes these four additional tools:

| Tool | Input | Result |
| --- | --- | --- |
| `run_suite` | `runtime`: `native` or `docker` | Immediate owned `run_id` and bounded job state |
| `get_run` | `run_id` | Current state, diagnostics, log path, and completed suite path |
| `cancel_run` | `run_id` | Immediate cancellation request; poll for cleanup completion |
| `compare_run_to_baseline` | `run_id`, `name` | Existing deterministic comparison for a completed owned run |

There are no tool arguments for shell commands, process IDs, environment
variables, project paths, configuration changes, or baseline promotion. The
server freezes validated configuration before each job and starts a fixed
isolated Python worker. Adapter hooks and the simulation environment selected
before server startup remain trusted operator configuration; logs and artifacts
cannot extend that authority. Configure the client to approve state-changing
tools according to its own policy.

The server limits each suite to `--max-run-sec` (default **3600 seconds**, finite
and at most 86400). It rejects a configured suite whose conservative runtime
budget exceeds that limit before starting a process. The budget sums existing
per-scenario watchdogs and allows native provenance probes or Docker build/probes.
Forced process cleanup adds at most 7 seconds on POSIX or 12 seconds for a managed
Windows worker, including its cooperative grace. The parent's Docker cleanup has
a separate 15-second total deadline. Navigation timeout remains the configured behavior
deadline and is distinct from the managed suite watchdog.

Only one managed job can own runtime resources at a time. An OS advisory lock
also rejects a concurrent job from another managed server. Run ordinary CLI
commands sequentially with managed jobs; manual CLI runs do not participate in
this managed lock and parallel suites remain unsupported.

Each job writes to `.robotci/runs/<run_id>/`, with a configuration snapshot,
`runtime.log`, atomic `run.json` state, and its own result/replay artifacts.
The existing `.robotci/suite-result.json` and saved baselines are unchanged.
`suite_path` stays null while a job runs. It is exposed only when the whole suite
and its referenced results match the frozen task, runtime, plan fingerprint, and
process exit. On cancellation, watchdog expiry, invalid evidence, or unconfirmed
cleanup, partial result artifacts are removed and never advertised as a completed
suite. Completed `FAIL`, `TIMEOUT`, and `INFRA_ERROR` suites remain distinguishable
from failure of the managed worker itself.

States are `RUNNING`, `CANCELLING`, `COMPLETED`, `CANCELLED`, `TIMED_OUT`, or `FAILED`.
`suite_status` is a separate deterministic robot verdict, present only for a
completed suite. Cancellation is idempotent for terminal jobs and refuses unknown
or foreign IDs. Jobs are owned by the server session: a restart does not adopt
processes or permit cancellation from persisted JSON. At most 128 jobs are retained
in one server's in-memory catalog; their disk artifacts survive shutdown.

Normal server shutdown requests cancellation and waits for bounded cleanup.
Linux helpers retain separate ownership markers, with an additional unique
managed-job marker for the outer server's descendant cleanup;
Docker run/probe containers use job-specific names. Forced Docker cleanup can
remove only strict matching names for that job, including when a Windows client
process was terminated. A separate worker-held OS lease remains locked through
independent cleanup if a stdio client kills the server before cleanup finishes.
The worker detects loss of the exact parent reservation without relying on a
possibly reused PID. It records `worker.json` and a non-PASS terminal `run.json`;
only the owning server can validate and publish a completed suite. Do not treat
an unvalidated worker exit as a robot verdict. Machine loss or forcibly killing
the entire process tree can prevent daemon cleanup; this local tool is not a
persistent job scheduler, and those abnormal cases require resource inspection.

Keep persistent evidence in result artifacts, not only in a chat. Open a completed
job with `robotci view --suite <suite_path>` or compare its path through the existing
CLI. Promote an accepted baseline separately after reviewing the measurements.

## Reference client

The dependency-light [reference workflow](../examples/mcp-agent/reference_client.py)
uses stdio MCP and no model/provider framework. From an activated checkout:

```powershell
python examples/mcp-agent/reference_client.py --project-root examples/nav2-loopback --baseline known-good
python examples/mcp-agent/reference_client.py --project-root examples/nav2-loopback --baseline known-good --run --runtime native
```

The first command inspects the existing latest suite. The second explicitly
enables a simulation job, polls its owned ID, and compares completed PASS evidence
with the existing named baseline. Interruption requests owned cancellation and
polls terminal cleanup before closing stdio. Requests and polling have explicit
deadlines; transport or input errors return infrastructure exit `3`.
Exit codes preserve the deterministic gate: `0` PASS, `4` REGRESSION, and runtime
failure/timeout codes for unsuccessful runs. The client neither creates baselines
nor interprets artifact text as instructions. Add model explanations downstream
of the returned structured measurements; models do not compute RobotCI verdicts.
