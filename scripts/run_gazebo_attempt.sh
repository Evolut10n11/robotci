#!/usr/bin/env bash
# The Nav2 demo is the subject of this adapter; RobotCI result semantics stay unchanged.
set -Eeo pipefail

if [ ! -f /opt/ros/jazzy/setup.bash ]; then
  echo "RobotCI Gazebo error: ROS 2 Jazzy is unavailable." >&2
  exit 3
fi
# shellcheck disable=SC1091
source /opt/ros/jazzy/setup.bash
if [ "${ROS_DISTRO:-}" != jazzy ] || ! command -v gz >/dev/null; then
  echo "RobotCI Gazebo error: Jazzy and Gazebo Harmonic are required." >&2
  exit 3
fi
case "${ROBOTCI_ROS_NAMESPACE:-}" in
  ""|/) ;;
  *) echo "RobotCI Gazebo adapter currently requires the root ROS namespace." >&2; exit 3 ;;
esac

PYTHON_BIN="${ROBOTCI_PYTHON:-python3}"
RESULT_FILE="${ROBOTCI_RESULT_FILE:?ROBOTCI_RESULT_FILE is required}"
PARAMS_FILE="${ROBOTCI_GAZEBO_PARAMS_FILE:?ROBOTCI_GAZEBO_PARAMS_FILE is required}"
START_X="${ROBOTCI_START_X:?ROBOTCI_START_X is required}"
START_Y="${ROBOTCI_START_Y:?ROBOTCI_START_Y is required}"
START_YAW="${ROBOTCI_START_YAW:?ROBOTCI_START_YAW is required}"
GOAL_X="${ROBOTCI_GOAL_X:?ROBOTCI_GOAL_X is required}"
GOAL_Y="${ROBOTCI_GOAL_Y:?ROBOTCI_GOAL_Y is required}"
GOAL_YAW="${ROBOTCI_GOAL_YAW:?ROBOTCI_GOAL_YAW is required}"
TIMEOUT_SEC="${ROBOTCI_TIMEOUT_SEC:?ROBOTCI_TIMEOUT_SEC is required}"
SCENARIO="${ROBOTCI_SCENARIO:?ROBOTCI_SCENARIO is required}"

BRINGUP_DIR="$(timeout --kill-after=2s 10s ros2 pkg prefix --share nav2_bringup)"
SIM_DIR="$(timeout --kill-after=2s 10s ros2 pkg prefix --share nav2_minimal_tb4_sim)"
DESCRIPTION_DIR="$(timeout --kill-after=2s 10s ros2 pkg prefix --share nav2_minimal_tb4_description)"
MAP_FILE="${ROBOTCI_GAZEBO_MAP_FILE:-$BRINGUP_DIR/maps/depot.yaml}"
WORLD_FILE="${ROBOTCI_GAZEBO_WORLD_FILE:-$SIM_DIR/worlds/depot.sdf}"
LAUNCH_FILE="${ROBOTCI_GAZEBO_LAUNCH_FILE:-$BRINGUP_DIR/launch/tb4_simulation_launch.py}"
for input in "$PARAMS_FILE" "$MAP_FILE" "$WORLD_FILE" "$LAUNCH_FILE"; do
  if [ ! -f "$input" ]; then
    echo "RobotCI Gazebo error: input does not exist: $input" >&2
    exit 3
  fi
done

mkdir -p "$(dirname -- "$RESULT_FILE")"
ATTEMPT_DIR="$(mktemp -d /tmp/robotci-gazebo.XXXXXXXX)"
# Gazebo transport has its own discovery scope. Randomness isolates processes;
# it does not change a robot/task/configuration input or the harness fingerprint.
export GZ_PARTITION="robotci-$(basename -- "$ATTEMPT_DIR")"
export GZ_SIM_RESOURCE_PATH="$SIM_DIR/worlds${GZ_SIM_RESOURCE_PATH:+:$GZ_SIM_RESOURCE_PATH}"
# Fixed adapter-owned rendering controls survive the core's admitted-environment
# filter. Harmonic uses EGL for lidar rendering without an X server or GUI.
export LIBGL_ALWAYS_SOFTWARE=1
export QT_QPA_PLATFORM=offscreen
RENDERED_WORLD="$ATTEMPT_DIR/world.sdf"
GAZEBO_LOG="${RESULT_FILE%.*}.gazebo.log"
LAUNCH_LOG="${RESULT_FILE%.*}.nav2.log"
SPAWN_LOG="${RESULT_FILE%.*}.spawn.log"
READINESS_FILE="${RESULT_FILE%.*}.gazebo.json"
PROCESSES=()

cleanup() {
  local status=$?
  set +e
  trap - EXIT INT TERM
  # Per-partition environment ownership survives launch-parent exit and setsid
  # children. Linux process start times protect against recycled PIDs. Cleanup
  # signals only owned individuals and verifies their real death within 7 s.
  timeout --foreground --kill-after=2s 10s "$PYTHON_BIN" -S -B -P \
    -m robotci.ros.gazebo_cleanup --output "$READINESS_FILE" || status=3
  for process in "${PROCESSES[@]}"; do
    # Bash has already collected completed background jobs. Do not wait
    # indefinitely on an uninterruptible kernel task even after SIGKILL.
    if ! kill -0 "$process" 2>/dev/null; then
      wait "$process" 2>/dev/null || true
    fi
  done
  rm -rf -- "$ATTEMPT_DIR"
  exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

# Rendering before gz starts avoids the upstream xacro/world-file startup race.
# SceneBroadcaster exposes model state for the independent physical-start check;
# gz runs server-only, so this does not create a GUI.
timeout --kill-after=2s 15s xacro -o "$RENDERED_WORLD" headless:=False "$WORLD_FILE"
setsid gz sim -v3 -r -s --headless-rendering "$RENDERED_WORLD" >"$GAZEBO_LOG" 2>&1 &
PROCESSES+=("$!")

# The official launch still provides state publishing, bridges and Nav2. Its
# simulator/spawn actions are disabled: the freshly rendered world is already
# running and the physical robot is explicitly created below.
setsid ros2 launch "$LAUNCH_FILE" \
  use_simulator:=False headless:=True use_rviz:=False \
  use_sim_time:=true use_namespace:=false \
  autostart:=true use_respawn:=False \
  map:="$MAP_FILE" world:="$WORLD_FILE" params_file:="$PARAMS_FILE" \
  robot_name:=nav2_turtlebot4 \
  x_pose:="$START_X" y_pose:="$START_Y" yaw:="$START_YAW" \
  >"$LAUNCH_LOG" 2>&1 &
PROCESSES+=("$!")

setsid timeout --kill-after=2s 45s ros2 run ros_gz_sim create \
  -name nav2_turtlebot4 -allow_renaming false -topic robot_description \
  -x "$START_X" -y "$START_Y" -z 0.01 -R 0 -P 0 -Y "$START_YAW" \
  >"$SPAWN_LOG" 2>&1 &
PROCESSES+=("$!")

READINESS_ARGS=(
  --start-x "$START_X" --start-y "$START_Y" --start-yaw "$START_YAW"
  --goal-x "$GOAL_X" --goal-y "$GOAL_Y"
  --map "$MAP_FILE" --world "$WORLD_FILE" --rendered-world "$RENDERED_WORLD"
  --params "$PARAMS_FILE" --launch "$LAUNCH_FILE"
  --sim-share "$SIM_DIR" --description-share "$DESCRIPTION_DIR"
  --output "$READINESS_FILE" --timeout-sec 135
)
set +e
timeout --foreground --kill-after=3s 145s "$PYTHON_BIN" -S -B -P \
  -m robotci.ros.gazebo_readiness "${READINESS_ARGS[@]}"
READY_EXIT=$?
set -e
if [ "$READY_EXIT" -ne 0 ]; then
  echo "RobotCI Gazebo readiness failed (exit $READY_EXIT)." >&2
  tail -n 80 "$GAZEBO_LOG" "$LAUNCH_LOG" "$SPAWN_LOG" >&2 || true
  exit 3
fi
if ! wait "${PROCESSES[2]}"; then
  echo "RobotCI Gazebo error: physical robot creation failed." >&2
  exit 3
fi
# The finished spawn PID may be recycled during a long navigation task. It is
# no longer a child we can safely identify by PID; partition cleanup covers any
# surviving descendants independently.
PROCESSES=("${PROCESSES[0]}" "${PROCESSES[1]}")

NAVIGATION_BUDGET="$("$PYTHON_BIN" -S -B -P -c \
  'import math,sys; t=float(sys.argv[1]); assert math.isfinite(t) and t>0; print(t+30)' \
  "$TIMEOUT_SEC")"
set +e
timeout --foreground --kill-after=3s "$NAVIGATION_BUDGET" \
  "$PYTHON_BIN" -S -B -P -m robotci.ros.navigation_scenario \
  --scenario "$SCENARIO" \
  --start-x "$START_X" --start-y "$START_Y" --start-yaw "$START_YAW" \
  --goal-x "$GOAL_X" --goal-y "$GOAL_Y" --goal-yaw "$GOAL_YAW" \
  --map-id "${ROBOTCI_MAP_ID:-depot}" --output "$RESULT_FILE" \
  --timeout-sec "$TIMEOUT_SEC" \
  --goal-tolerance-m "${ROBOTCI_GOAL_TOLERANCE_M:-0.25}" \
  --min-feedback-samples "${ROBOTCI_MIN_FEEDBACK_SAMPLES:-1}"
SCENARIO_EXIT=$?
set -e
if [ "$SCENARIO_EXIT" -gt 3 ]; then
  echo "RobotCI Gazebo probe failed outside the result contract (exit $SCENARIO_EXIT)." >&2
  exit 3
fi
if ! timeout --foreground --kill-after=3s 15s "$PYTHON_BIN" -S -B -P \
  -m robotci.ros.gazebo_readiness "${READINESS_ARGS[@]}" --verify-only; then
  echo "RobotCI Gazebo error: post-navigation controller verification failed." >&2
  exit 3
fi
exit "$SCENARIO_EXIT"
