# Runtime verdict integrity

RobotCI must not interpret a previous run's artifacts as evidence that the current
run passed. This applies to single scenarios, suites, Docker staging artifacts,
and the native wrapper's one permitted Loopback startup retry.

## Fresh results and consistent verdicts

Before starting each scenario, RobotCI removes the target result and its associated
replay. Docker also clears the host-side staging result/replay before starting the
container. The native wrapper clears the result, replay, and race-detection log
before **each** attempt, including a retry. A stale race log cannot trigger a retry.
Failure to clear an artifact prevents that runtime attempt from starting.
The wrapper invokes the shared Python `default_replay_path` helper for cleanup,
using the same Python selection as the native attempt. It does not reimplement
filename suffix rules in Bash; hidden, extensionless and unusual names follow
the active Python version's rules exactly.

A result must be a JSON object for the requested scenario, have a recognized
status and a finite, non-negative numeric `duration_sec`, and agree with the
process exit code:

| Status | Exit code |
| --- | --- |
| PASS | 0 |
| FAIL | 1 |
| TIMEOUT | 2 |
| INFRA_ERROR | 3 |

Missing, malformed, foreign-scenario or contradictory results fail closed with
exit code 3. RobotCI writes a compact `INFRA_ERROR` artifact with the scenario name,
`runtime_exit_code`, and an error message, and removes any misleading replay. It
does not invent navigation telemetry for an attempt without valid results. The
scenario file, suite entry, and suite verdict therefore cannot disagree about a
PASS when the runtime failed. Valid FAIL and TIMEOUT results retain their verdicts.

Output files are intentionally replaced on a new attempt. Store known-good
baselines separately. Concurrent runs targeting the same output/staging paths are
not supported; use separate working copies and output paths for concurrent jobs.

## Navigation completion evidence

The Nav2 completion poll can deliver the last feedback message while it spins
the ROS executor. RobotCI collects that message before evaluating the result,
including its observed position and recovery count. Cached feedback is
deduplicated; neither a completed action nor its requested goal substitutes for
an observed final pose. Missing or invalid feedback retains the evidence policy's
existing failure semantics.

The navigation deadline starts at goal dispatch. Completion observed at or after
that deadline remains `TIMEOUT`, with the available telemetry preserved. A task
that has already completed is not canceled again.

## Runtime watchdog

Navigation `TIMEOUT` is distinct from a hung adapter, Nav2 call, or cleanup phase.
The outer runner bounds the complete runtime process independently of the
navigation probe. Timeout values must be finite and positive before runtime
selection or execution begins.

For a navigation timeout of `T` seconds, the process budgets are:

| Phase | Maximum budget |
| --- | --- |
| Native scenario wrapper | `2 × (180 + T + 30) + 1` seconds |
| Docker scenario using the suite's existing image | Native budget + 30 seconds |
| Standalone Docker scenario with image build | Native budget + 30 + 300 seconds |
| Docker environment capture before a suite | 300 seconds with build; otherwise 60 seconds |

The native budget allows two attempts because the wrapper can retry one known
Loopback startup race. The 180-second startup and 30-second cleanup values are
allowances in that total budget, not separate per-phase timers. Unhealthy startup
cannot consume the entire sum of the shell script's readiness retry limits.

On expiry the runner terminates its owned process group, allows up to five seconds
for shutdown, then kills surviving owned processes and bounds the leader wait to
two seconds. On Linux, descendant identities and an inherited per-run ownership
marker also identify detached Nav2 sessions. Process inventory requires a `/proc`
mount with the same PID namespace as signal delivery; otherwise only the safely
owned wrapper group is addressed. External adapters must preserve the ownership
marker in detached processes and remain responsible for normal cleanup.

Docker runs and environment probes receive unique container names. On expiry,
RobotCI force-removes only that run's container with a separate 15-second deadline;
it never tears down another run or the shared Compose project. If Docker is
unresponsive, removal cannot be guaranteed and the cleanup failure is reported.

An outer runtime expiry produces exit code `3`, `INFRA_ERROR`, and
`reason_code: runtime_watchdog_timeout`. Any partial result, including a `PASS`
written before cleanup hung, is replaced and its replay removed. The suite entry
and scenario artifact agree. An ordinary completed navigation timeout keeps exit
code `2`; a Docker environment-capture error stops before suite execution.

## Native readiness

The runner's selection routine is also used by the default doctor's blocking
runtime check. Native is selected only on Linux after a bounded Bash subprocess:

1. Sources `/opt/ros/jazzy/setup.bash` when installed, just like the native attempt.
2. Checks that `ros2` is available and the effective `ROS_DISTRO` is `jazzy`.
3. Resolves `nav2_bringup`, `nav2_loopback_sim`, and `nav2_simple_commander`.

The probe does not import ROS into the cross-platform Python core or modify the
parent process environment. A failed setup, missing package, wrong distribution,
missing command or probe timeout cannot make native ready. Auto selection falls
back to Docker when its daemon is available, otherwise it reports no usable
runtime. An existing setup file by itself is not sufficient evidence of readiness.

Doctor's individual ROS rows remain current-shell diagnostics. They can be warnings
while the default runtime check succeeds for an installed but unsourced Jazzy.
`--require-ros` retains its stricter current-shell requirements, and
`--runtime-optional` retains its non-blocking inventory behavior. Package discovery
is a readiness preflight, not proof that simulation or navigation will succeed;
the actual attempt must still produce a fresh, consistent result.

## Regression coverage

`tests/test_runtime_integrity.py` covers stale files, single/suite consistency,
Docker staging (including source equal to destination), malformed/foreign results,
valid status preservation, cleanup failures, and actual Bash retry cleanup.
`tests/test_native_runtime.py` runs the real probe against isolated executable
fixtures and temporary setup scripts, including unsourced Jazzy and Docker fallback.
`tests/test_navigation_completion.py` covers final feedback, cached samples,
recovery-only updates, missing/invalid poses, and completion at the deadline.
`tests/test_runtime_watchdog.py` covers bounded execution and owned-process
cleanup. `tests/test_runner.py` covers Docker removal, invalid timeouts, and
partial-result rejection; `tests/test_reproducibility.py` covers probe cleanup.
POSIX integration tests are skipped on Windows; cross-platform core tests still run.
