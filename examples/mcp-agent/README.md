# RobotCI MCP reference workflow

See the [MCP guide](../../docs/mcp.md#reference-client) for installation and usage.
`reference_client.py` demonstrates inspection or an explicitly requested
simulation job, bounded polling, owned cancellation, and deterministic baseline
comparison. It uses the optional MCP SDK without a provider or orchestration
framework. Prepare and review an existing named baseline before comparing a run.

No ROS runtime or physical robot is provided by this example. The ordinary
six-tool server remains read-only; `--run` starts a separate server with explicit
project/config selection and the four managed-job tools.
