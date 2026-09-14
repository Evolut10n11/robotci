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
POSIX integration tests are skipped on Windows; cross-platform core tests still run.
