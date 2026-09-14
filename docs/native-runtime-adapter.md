# Native runtime adapter hook

RobotCI's built-in native runtime uses the Nav2 Loopback stack, but external pilot repositories often already have their own simulator and Nav2 launch flow. For those cases, RobotCI supports an adapter hook without changing deterministic result semantics.

## Contract

Set `ROBOTCI_ATTEMPT_SCRIPT` to an executable-compatible shell script before running RobotCI with the native runtime:

```bash
export ROBOTCI_ATTEMPT_SCRIPT="$PWD/robotci_adapter.sh"
robotci run --runtime native --config robotci.yaml
```

RobotCI invokes the adapter with `bash` once per scenario. The adapter receives the same scenario contract as the built-in Nav2 Loopback attempt:

- `ROBOTCI_SCENARIO`
- `ROBOTCI_START_X`, `ROBOTCI_START_Y`, `ROBOTCI_START_YAW`
- `ROBOTCI_START_QZ`, `ROBOTCI_START_QW`
- `ROBOTCI_GOAL_X`, `ROBOTCI_GOAL_Y`, `ROBOTCI_GOAL_YAW`
- `ROBOTCI_RESULT_FILE`
- `ROBOTCI_TIMEOUT_SEC`
- `ROBOTCI_PYTHON`

The adapter is responsible for starting or connecting to the target simulator/Nav2 stack, executing the scenario, writing the normal RobotCI scenario result JSON to `ROBOTCI_RESULT_FILE`, and cleaning up processes that it starts.

Return codes keep the existing RobotCI contract:

- `0` — PASS
- `1` — FAIL
- `2` — TIMEOUT
- `3` — INFRA_ERROR

RobotCI does not let an adapter redefine regression policy: baseline/candidate comparison still consumes normalized RobotCI result files and remains deterministic.

## Minimal adapter skeleton

```bash
#!/usr/bin/env bash
set -Eeo pipefail

# Source the target workspace if needed.
source /opt/ros/jazzy/setup.bash
source "$HOME/target_ws/install/setup.bash"

# Start the repository's simulator/Nav2 launch in a process group.
setsid ros2 launch target_navigation navigation.launch.py > /tmp/robotci-target.log 2>&1 &
TARGET_PID=$!

cleanup() {
  set +e
  kill -TERM -- "-$TARGET_PID" 2>/dev/null || true
  wait "$TARGET_PID" 2>/dev/null || true
}
trap cleanup EXIT

# Perform repository-specific readiness checks here, then execute RobotCI's
# normalized Nav2 scenario probe against the running graph.
"${ROBOTCI_PYTHON:-python3}" -m robotci.ros.navigation_scenario \
  --scenario "$ROBOTCI_SCENARIO" \
  --start-x "$ROBOTCI_START_X" \
  --start-y "$ROBOTCI_START_Y" \
  --start-yaw "$ROBOTCI_START_YAW" \
  --goal-x "$ROBOTCI_GOAL_X" \
  --goal-y "$ROBOTCI_GOAL_Y" \
  --goal-yaw "$ROBOTCI_GOAL_YAW" \
  --output "$ROBOTCI_RESULT_FILE" \
  --timeout-sec "$ROBOTCI_TIMEOUT_SEC"
```

A real adapter should wait for the target stack's readiness signals before invoking the scenario probe. It should not require proprietary maps, credentials, production access, or a physical robot for pilot validation.

## External pilot use

For the first external pilot targets, prefer one small adapter script in the target checkout over adding target-specific behavior to RobotCI core. If two or more independent repositories require the same setup pattern, that repeated evidence is the signal to promote it into a first-class runtime adapter API.

For Clearpath's public Nav2 demos, the first pilot adapter should launch the Jazzy `a200` warehouse simulation/navigation stack, wait for `/navigate_to_pose`, then invoke the normalized scenario probe. Keep the adapter in the pilot workspace until the compatibility pattern is proven reusable.

## Limitations

This hook currently applies to the native runtime only. Docker execution uses RobotCI's own compose runtime and does not mount arbitrary host adapter scripts. Treat Docker adapter support as a separate feature only if pilot evidence requires it.
