# Native Nav2 / Gazebo runtime acceptance

Status on 2026-09-30: experiment prepared, simulation **not executed**. The
maintenance environment is Ubuntu 24.04 with Python 3.12, but has no `ros2`,
`gz`, Docker executable, or `/opt/ros/jazzy/setup.bash`. Unit tests and the
existing Loopback CI are not evidence that this Gazebo integration works.
This experiment contributes zero external participants to M8.

## Target and experiment boundary

Use the official Nav2 TurtleBot 4 Gazebo demo first, in an isolated Ubuntu
24.04 / ROS 2 Jazzy simulation workspace. Its empty ROS namespace avoids the
unresolved Clearpath namespace integration described in
[clearpath-preflight.md](clearpath-preflight.md).

The inspected upstream revision is
[`ros-navigation/navigation2@645abd95f2be02a13ca539b29c2ddc065db34f89`](https://github.com/ros-navigation/navigation2/tree/645abd95f2be02a13ca539b29c2ddc065db34f89).
The inspected
[Gazebo launch](https://github.com/ros-navigation/navigation2/blob/645abd95f2be02a13ca539b29c2ddc065db34f89/nav2_bringup/launch/tb4_simulation_launch.py)
requires `nav2_minimal_tb4_sim`, `nav2_minimal_tb4_description`, and Gazebo;
it launches `gz sim`, rather than the Loopback simulator. It defaults to
`depot.yaml`, `depot.sdf`, an empty namespace, and simulation time.
Pin the installed build/package versions and simulator assets as well as this
source revision; a source SHA alone does not identify an apt-installed runtime.

After provisioning those dependencies, this is the upstream headless smoke
launch, **not yet a RobotCI adapter or acceptance result**:

```bash
source /opt/ros/jazzy/setup.bash
ros2 launch nav2_bringup tb4_simulation_launch.py \
  headless:=True \
  use_rviz:=False \
  use_sim_time:=true \
  use_namespace:=false
```

Do not reuse RobotCI's Loopback coordinates. Inspect the actual depot map and
simulation, then select one collision-free start/goal and verify that the
baseline reaches it. Freeze those coordinates, map YAML/image/world digests,
goal tolerance, timeout, and feedback policy in `acceptance.yaml` before the
measurement series. Keep timeout large enough for the slower candidate to
finish: a `TIMEOUT` cannot demonstrate a completed metric-regression comparison.

## Integration work required before collection

Keep a small `robotci_adapter.sh` in the simulation workspace, following the
[native adapter contract](../native-runtime-adapter.md). The adapter must:

1. Start a fresh Gazebo world and robot at the scenario's start pose for **every**
   invocation, using the same map, world, controller config path, and launch
   arguments. Publishing `/initialpose` changes localization; it is not proof
   that the robot was physically reset in Gazebo.
2. Bound launch/readiness/reset waits, verify a progressing `/clock`, sensor
   topics and required TF, and wait for active Nav2 lifecycle nodes and the
   actual `/navigate_to_pose` endpoint. Verify the observed robot pose against
   the selected start before dispatching a goal.
3. Explicitly initialize localization, then invoke
   `robotci.ros.navigation_scenario` with all scenario/evidence inputs received
   through the adapter contract. Keep probe simulation time enabled.
4. Write to `ROBOTCI_RESULT_FILE`, propagate its real exit code, and clean up
   every child process it owns on success, failure and interruption. Use a fresh
   log per attempt and keep stale Loopback retry markers out of that log.
5. Record the simulator/controller read-back and target/config/asset digests
   beside each suite. Resolve any Gazebo-generated cache or asset download
   before freezing the environment and collecting comparable runs.

Implement and verify this adapter on the provisioned host before calling the
commands below. No untested Gazebo adapter is checked in as supported behavior.
`robotci doctor` checks the current Jazzy/Loopback requirements; it does not
validate the extra Gazebo dependencies or this adapter's reset/readiness logic.

## Keep the harness stable while changing the subject

The metric comparison requires identical execution fingerprints. Adapter bytes
and selected path, RobotCI code, runtime packages/import resources, inherited
ROS/middleware controls, effective task and evidence policies belong to the
harness and must remain unchanged throughout the series. Changing an adapter
to insert a delay or changing a ROS environment selector creates a different
experiment; it is not a comparable robot regression.

Prepare one explicit, versioned controller YAML as the subject under test
(SUT). The stable adapter must always read that same path. Record its full
content digest, exact changed key, and effective controller read-back before
and after each run; require no mid-run changes. Keep map/world/reset inputs
separate and invariant. The adapter hook does not automatically authenticate
these additional target files or the effective Gazebo state.

For a first deliberate real change, the inspected
[upstream MPPI parameters](https://github.com/ros-navigation/navigation2/blob/645abd95f2be02a13ca539b29c2ddc065db34f89/nav2_bringup/params/nav2_params.yaml)
set `controller_server.ros__parameters.FollowPath.vx_max` to `0.5` m/s.
Changing just that value to `0.2` m/s is a testable hypothesis that navigation
duration will increase. A gate result must come from measurement; the slower
cap is not a guaranteed `REGRESSION`. Verify that the selected runtime actually
uses MPPI and this parameter before collecting data.

Do not patch installed ROS/RobotCI code or resource trees to perform that
experiment. Those trees are pinned by the harness. If the selected controller
change also changes the current execution fingerprint, stop and record the
compatibility blocker. Do not rewrite saved fingerprints or weaken comparison
checks to force a verdict. A more general separately versioned SUT provenance
contract is follow-up work if real targets need implementation/package changes.

RobotCI currently labels a native adapter with the runtime contract
`ros2-nav2-jazzy-loopback-v1`. That label alone is not evidence of Gazebo
compatibility or complete Gazebo provenance; include the explicit target
manifest and adapter verification with this experiment.

## Measurement series

Run from the provisioned simulation workspace containing the verified
`acceptance.yaml` and `robotci_adapter.sh`. Freeze RobotCI at one reviewed
revision for the entire experiment and use one host/session with no dependency
installation between runs.

```bash
export ROBOTCI_ATTEMPT_SCRIPT="$PWD/robotci_adapter.sh"
robotci validate --config "$PWD/acceptance.yaml"
robotci plan --config "$PWD/acceptance.yaml"
robotci doctor

for attempt in 1 2 3 4 5; do
  robotci run --runtime native --config "$PWD/acceptance.yaml" \
    --output "$PWD/evidence/baseline-$attempt/suite-result.json" || exit "$?"
done
```

Review all five complete result/replay sets. For each scenario record duration,
path length, distance to goal, feedback quality, recoveries, and stuck events.
Calculate the range and median of navigation duration/path length and compare
every ordered pair with the intended regression policy. If unchanged runs
already trigger regressions, stop: the default 10% policy has not been validated
for this environment. Upstream MPPI uses random sampling; repeated runs are
required even when poses and configuration are fixed. Five runs establish an
initial engineering check, not a statistical false-positive guarantee.

Use baseline run 1 under a rule decided before collection; do not select the
fastest or most favorable run after reviewing the candidate. If the unchanged
series passes review, capture run 1:

```bash
robotci-baseline save gazebo-known-good \
  --suite "$PWD/evidence/baseline-1/suite-result.json" \
  --store "$PWD/evidence/baselines"

robotci run --runtime native --config "$PWD/acceptance.yaml" \
  --output "$PWD/evidence/control/suite-result.json"
robotci-baseline gate gazebo-known-good \
  --store "$PWD/evidence/baselines" \
  --candidate "$PWD/evidence/control/suite-result.json" \
  --output "$PWD/evidence/control-gate.json" \
  --markdown-output "$PWD/evidence/control-gate.md" \
  --junit-output "$PWD/evidence/control-gate.xml"
```

Require the held-out unchanged control to pass. Next apply the single recorded
SUT parameter edit, restart through the same adapter, verify parameter read-back,
and collect the candidate:

```bash
robotci run --runtime native --config "$PWD/acceptance.yaml" \
  --output "$PWD/evidence/candidate/suite-result.json"
robotci-baseline gate gazebo-known-good \
  --store "$PWD/evidence/baselines" \
  --candidate "$PWD/evidence/candidate/suite-result.json" \
  --output "$PWD/evidence/candidate-gate.json" \
  --markdown-output "$PWD/evidence/candidate-gate.md" \
  --junit-output "$PWD/evidence/candidate-gate.xml" \
  && gate_exit=0 || gate_exit=$?
printf 'Candidate gate exit: %s\n' "$gate_exit"

robotci view --suite "$PWD/evidence/candidate/suite-result.json" \
  --baseline-suite "$PWD/evidence/baselines/gazebo-known-good/suite-result.json" \
  --port 0
```

Record the printed gate exit code: `0` means within policy, `4` means measured
regression, and `3` means invalid/incompatible comparison, not a completed
comparison. Inspect the named findings and both trajectories. Restore the
baseline controller YAML, record its original digest/read-back, and repeat the
held-out control to test whether drift or leaked state explains the candidate.
Keep all failed attempts; do not adjust thresholds after seeing the candidate.

## Completion evidence

The internal case is complete only with a dated target/harness/SUT manifest,
verified reset/readiness/cleanup, five unchanged runs, passing held-out and
restored controls, a completed real candidate gate, its JSON/Markdown/JUnit,
and recorded replays consistent with the scenario metrics. An unexpected
`PASS` is an honest completed measurement but does not establish that the
deliberate slowdown is detected. A regression-detection claim additionally
requires measured findings that match the intervention and stable controls.

Then have an independent engineer reproduce the same documented workflow on
their own simulation project. Internal use of upstream sources is neither
upstream endorsement nor an external-team outcome. Keep the M8 register
unchanged until actual participants and observations exist.
