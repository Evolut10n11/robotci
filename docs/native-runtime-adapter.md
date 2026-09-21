# Native runtime adapter hook

RobotCI's built-in native runtime uses the Nav2 Loopback stack, but external pilot repositories often already have their own simulator and Nav2 launch flow. For those cases, RobotCI supports an adapter hook without changing deterministic result semantics.

## Contract

Set `ROBOTCI_ATTEMPT_SCRIPT` to an executable-compatible shell script before running RobotCI with the native runtime. Resolve the target configuration to an absolute path from the pilot checkout so RobotCI cannot silently fall back to its own package checkout:

```bash
export ROBOTCI_ATTEMPT_SCRIPT="$PWD/robotci_adapter.sh"
robotci run --runtime native --config "$PWD/robotci.yaml"
```

RobotCI invokes the adapter with `bash` for each scenario. Normally there is one invocation. If an invocation returns `3` (`INFRA_ERROR`) and the runtime log contains RobotCI's two known Nav2 Loopback empty-map race markers, the wrapper may retry the same scenario once. External adapters must therefore make setup/cleanup safe to repeat. When the adapter does not use the built-in Loopback log, clear stale `/tmp/nav2-<scenario>.log` files before a pilot run or point `ROBOTCI_LOG_FILE` at a fresh log file so old Loopback markers cannot trigger an accidental retry.

The adapter receives the same scenario contract as the built-in Nav2 Loopback attempt:

- `ROBOTCI_SCENARIO`
- `ROBOTCI_START_X`, `ROBOTCI_START_Y`, `ROBOTCI_START_YAW`
- `ROBOTCI_START_QZ`, `ROBOTCI_START_QW`
- `ROBOTCI_GOAL_X`, `ROBOTCI_GOAL_Y`, `ROBOTCI_GOAL_YAW`
- `ROBOTCI_MAP_ID`
- `ROBOTCI_RESULT_FILE`
- `ROBOTCI_TIMEOUT_SEC`
- `ROBOTCI_PYTHON`

The adapter is responsible for starting or connecting to the target simulator/Nav2 stack, placing or localizing the simulated robot at the configured start pose, executing the scenario, writing the normal RobotCI scenario result JSON to `ROBOTCI_RESULT_FILE`, and cleaning up processes that it starts.

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

# Perform repository-specific readiness checks here.
#
# Before the probe starts, the simulator/localization state must match the
# configured RobotCI start pose. If the target supports /initialpose, publish it
# explicitly. Targets that require a simulator reset/teleport service should do
# that first and only continue after the robot really occupies this pose.
timeout 20s ros2 topic pub --once \
  /initialpose geometry_msgs/msg/PoseWithCovarianceStamped \
  "{header: {frame_id: map}, pose: {pose: {position: {x: $ROBOTCI_START_X, y: $ROBOTCI_START_Y, z: 0.0}, orientation: {x: 0.0, y: 0.0, z: $ROBOTCI_START_QZ, w: $ROBOTCI_START_QW}}}}"

# Execute RobotCI's normalized Nav2 scenario probe against the running graph.
"${ROBOTCI_PYTHON:-python3}" -m robotci.ros.navigation_scenario \
  --scenario "$ROBOTCI_SCENARIO" \
  --start-x "$ROBOTCI_START_X" \
  --start-y "$ROBOTCI_START_Y" \
  --start-yaw "$ROBOTCI_START_YAW" \
  --goal-x "$ROBOTCI_GOAL_X" \
  --goal-y "$ROBOTCI_GOAL_Y" \
  --goal-yaw "$ROBOTCI_GOAL_YAW" \
  --map-id "$ROBOTCI_MAP_ID" \
  --output "$ROBOTCI_RESULT_FILE" \
  --timeout-sec "$ROBOTCI_TIMEOUT_SEC"
```

A real adapter should wait for the target stack's readiness signals before applying the start pose and invoking the scenario probe. Do not treat the `--start-*` arguments passed to `navigation_scenario` as a simulator reset: they seed RobotCI's metric/result contract, while the adapter itself must make the target robot state match them. The adapter should not require proprietary maps, credentials, production access, or a physical robot for pilot validation.

Set each scenario's `map_id` to a stable map name or content digest. The value is
part of RobotCI's task fingerprint together with the scenario, start, goal, and
coordinate frame. A controller or planner change remains comparable because its
implementation identity is deliberately outside the task fingerprint.

## External pilot use

For the first external pilot targets, prefer one small adapter script in the target checkout over adding target-specific behavior to RobotCI core. If two or more independent repositories require the same setup pattern, that repeated evidence is the signal to promote it into a first-class runtime adapter API.

For Clearpath's public Nav2 demos, first launch a separate Clearpath simulator;
the demo package only adds navigation and localization to an already running robot.
Select the Jazzy `a200` platform through the simulator's `robot.yaml`, then start
warehouse localization and navigation with simulation time. Wait for the actual
namespaced Nav2 action, explicitly reset/localize the robot at RobotCI's configured
start pose, and invoke the normalized scenario probe in the same ROS namespace
and TF/topic context. Do not assume a global `/navigate_to_pose` endpoint. Keep the
adapter in the pilot workspace until the compatibility pattern is proven reusable.
The [Clearpath preflight](validation/clearpath-preflight.md) records the verified
source revision, current runtime blocker, and the remaining acceptance checks.

## Limitations

This hook currently applies to the native runtime only. Docker execution uses RobotCI's own compose runtime and does not mount arbitrary host adapter scripts. Treat Docker adapter support as a separate feature only if pilot evidence requires it.
