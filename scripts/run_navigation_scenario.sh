#!/usr/bin/env bash
set -Eeo pipefail

if [ -f /opt/ros/jazzy/setup.bash ]; then
  # shellcheck disable=SC1091
  source /opt/ros/jazzy/setup.bash
fi

if ! command -v ros2 >/dev/null 2>&1; then
  echo "RobotCI runtime error: ros2 was not found."
  echo "Use Ubuntu 24.04 with ROS2 Jazzy/Nav2 installed or run the Docker image."
  exit 3
fi

if [ "${ROS_DISTRO:-}" != "jazzy" ]; then
  echo "RobotCI runtime error: expected ROS_DISTRO=jazzy, got '${ROS_DISTRO:-unset}'."
  exit 3
fi

SCENARIO="${ROBOTCI_SCENARIO:-simple_route}"
START_X="${ROBOTCI_START_X:-0.0}"
START_Y="${ROBOTCI_START_Y:-0.0}"
START_YAW="${ROBOTCI_START_YAW:-0.0}"
START_QZ="${ROBOTCI_START_QZ:-0.0}"
START_QW="${ROBOTCI_START_QW:-1.0}"
GOAL_X="${ROBOTCI_GOAL_X:-17.86}"
GOAL_Y="${ROBOTCI_GOAL_Y:--0.77}"
GOAL_YAW="${ROBOTCI_GOAL_YAW:-0.0}"
LOG_FILE="${ROBOTCI_LOG_FILE:-/tmp/nav2-${SCENARIO}.log}"
RESULT_FILE="${ROBOTCI_RESULT_FILE:-artifacts/${SCENARIO}/result.json}"
TIMEOUT_SEC="${ROBOTCI_TIMEOUT_SEC:-120}"

PYTHON_BIN="${ROBOTCI_PYTHON:-python3}"
if [ -x ".venv/bin/python" ]; then
  PYTHON_BIN=".venv/bin/python"
fi

mkdir -p "$(dirname "$RESULT_FILE")"

# A suite executes multiple scenarios in the same CI job. Make sure the ROS CLI
# graph cache from a previous scenario cannot leak stale nodes/services into the
# next run.
ros2 daemon stop >/dev/null 2>&1 || true

# Start the complete Nav2 launch in its own process group. Killing only the
# ros2-launch parent can leave composed Nav2 child processes alive, which makes
# the next scenario discover stale lifecycle services and hang indefinitely.
setsid ros2 launch nav2_bringup tb4_loopback_simulation.launch.py \
  use_rviz:=False \
  autostart:=False \
  >"$LOG_FILE" 2>&1 &
NAV2_PID=$!

cleanup() {
  set +e

  kill -TERM -- "-$NAV2_PID" 2>/dev/null || true

  for _ in $(seq 1 20); do
    if ! kill -0 "$NAV2_PID" 2>/dev/null; then
      break
    fi
    sleep 0.25
  done

  kill -KILL -- "-$NAV2_PID" 2>/dev/null || true
  wait "$NAV2_PID" 2>/dev/null || true
  ros2 daemon stop >/dev/null 2>&1 || true
}
trap cleanup EXIT

lifecycle_active() {
  local state
  state="$(timeout 10s ros2 lifecycle get "$1" 2>/dev/null || true)"
  [[ "$state" == *"active [3]"* ]]
}

wait_for_service() {
  local service_name="$1"
  for attempt in $(seq 1 60); do
    local services
    services="$(timeout 10s ros2 service list 2>/dev/null || true)"
    if printf '%s\n' "$services" | grep -qx "$service_name"; then
      return 0
    fi
    echo "Waiting for service $service_name ($attempt/60)..."
    sleep 1
  done
  return 1
}

wait_for_node() {
  local node_name="$1"
  for attempt in $(seq 1 60); do
    local nodes
    nodes="$(timeout 10s ros2 node list 2>/dev/null || true)"
    if printf '%s\n' "$nodes" | grep -qx "$node_name"; then
      return 0
    fi
    echo "Waiting for node $node_name ($attempt/60)..."
    sleep 1
  done
  return 1
}

call_startup() {
  local service_name="$1"
  local output

  output="$(
    timeout 20s ros2 service call \
      "$service_name" \
      nav2_msgs/srv/ManageLifecycleNodes \
      "{command: 0}" \
      2>&1
  )" || {
    echo "$output"
    return 1
  }

  echo "$output"
  [[ "$output" == *"success=True"* ]]
}

fail_with_log() {
  echo "$1"
  if [ -f "$LOG_FILE" ]; then
    echo "----- Nav2 log -----"
    cat "$LOG_FILE"
  fi
  exit 3
}

wait_for_node /loopback_simulator || fail_with_log "Loopback simulator did not appear"
wait_for_service /lifecycle_manager_map_server/manage_nodes \
  || fail_with_log "Map lifecycle manager service did not appear"
wait_for_service /lifecycle_manager_navigation/manage_nodes \
  || fail_with_log "Navigation lifecycle manager service did not appear"

echo "Starting map server lifecycle..."
call_startup /lifecycle_manager_map_server/manage_nodes \
  || fail_with_log "Map server lifecycle startup failed"

for attempt in $(seq 1 30); do
  if lifecycle_active /map_server; then
    break
  fi
  if [ "$attempt" -eq 30 ]; then
    fail_with_log "map_server did not become active"
  fi
  sleep 1
done

echo "Setting Loopback start pose = ($START_X, $START_Y, $START_YAW)..."
timeout 20s ros2 topic pub --once /initialpose geometry_msgs/msg/PoseWithCovarianceStamped \
  "{header: {frame_id: map}, pose: {pose: {position: {x: $START_X, y: $START_Y, z: 0.0}, orientation: {x: 0.0, y: 0.0, z: $START_QZ, w: $START_QW}}}}" \
  || fail_with_log "Publishing initial pose timed out"

sleep 2

echo "Starting navigation lifecycle..."
call_startup /lifecycle_manager_navigation/manage_nodes \
  || fail_with_log "Navigation lifecycle startup failed"

READY=0
for attempt in $(seq 1 60); do
  actions="$(timeout 10s ros2 action list 2>/dev/null || true)"
  if printf '%s\n' "$actions" | grep -qx '/navigate_to_pose' \
    && lifecycle_active /bt_navigator \
    && lifecycle_active /planner_server \
    && lifecycle_active /controller_server; then
    READY=1
    break
  fi
  echo "Waiting for navigation readiness ($attempt/60)..."
  sleep 1
done

if [ "$READY" -ne 1 ]; then
  fail_with_log "Nav2 did not become ready"
fi

echo "Running RobotCI scenario: $SCENARIO"
set +e
"$PYTHON_BIN" -m robotci.ros.navigation_scenario \
  --scenario "$SCENARIO" \
  --start-x "$START_X" \
  --start-y "$START_Y" \
  --start-yaw "$START_YAW" \
  --goal-x "$GOAL_X" \
  --goal-y "$GOAL_Y" \
  --goal-yaw "$GOAL_YAW" \
  --output "$RESULT_FILE" \
  --timeout-sec "$TIMEOUT_SEC"
SCENARIO_EXIT=$?
set -e

echo "Scenario result:"
if [ -f "$RESULT_FILE" ]; then
  cat "$RESULT_FILE"
else
  echo "Result file was not created: $RESULT_FILE"
fi

exit "$SCENARIO_EXIT"
