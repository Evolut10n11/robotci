# Nav2 / Gazebo controller acceptance

This example runs a real TurtleBot 4 in Gazebo Harmonic with ROS 2 Jazzy on
Ubuntu 24.04. The route is checked against the depot occupancy map before
navigation. It is an internal integration experiment, not an external M8 pilot.
The first nine-run cohort with conditional replanning detected the real speed
intervention. Its independent same-head repetition passed 19 of 20 unchanged
gates but failed final-distance stability, despite stable timing and no recoveries
or stuck events. Repeatable acceptance is not established. The next fixed
experiment adds RotationShim and awaits a full series plus independent repetition.

## Run the complete experiment

Use the repository's [Gazebo Acceptance workflow](../../.github/workflows/gazebo-acceptance.yml).
It provisions the simulator, freezes the installed package versions and the
pinned Nav2 launch source, and selects Twist or TwistStamped from the installed
TurtleBot bridge configuration. No Docker or ROS installation is required on
the computer from which the workflow is requested.

The workflow performs a warm-up, five unchanged baseline runs, all twenty
ordered baseline comparisons, an independent unchanged control, one MPPI
`FollowPath.vx_max` intervention from `0.5` to `0.2 m/s`, and a restored control.
Baseline 1 is selected before measurement. The default regression policy stays
unchanged throughout the experiment.

For the next fixed experiment, freeze this setup before warm-up and keep it the
same for every run:

| Nav2 setting | Value |
| --- | --- |
| `FollowPath.plugin` | `nav2_rotation_shim_controller::RotationShimController` |
| `FollowPath.primary_controller` | `nav2_mppi_controller::MPPIController` |
| `FollowPath.rotate_to_goal_heading` | `true` |
| `FollowPath.visualize` | `false` |
| `FollowPath.regenerate_noises` | `false` |
| `general_goal_checker.stateful` | `true` |
| `general_goal_checker.xy_goal_tolerance` | `0.20 m` |
| `general_goal_checker.yaw_goal_tolerance` | `0.25 rad` |
| `FollowPath.GoalAngleCritic.threshold_to_consider` | `0.20 m` |

This disables trajectory visualization and repeated noise generation, uses
Nav2's position latch before final orientation, and matches final-heading cost
activation to the XY capture boundary. RotationShim wraps MPPI in the same
`FollowPath` namespace. These settings are an unverified structural hypothesis.
The adapter must verify the actual wrapper plugin, primary controller, heading
flag, preset, and speed before and after navigation.
Controller frequency remains `20 Hz`, batch size remains `2000`, and the
intervention changes only `vx_max`. This preset does not guarantee deterministic
navigation; the five unchanged baselines must still pass all default gates.

## Fixed behavior-tree evidence

The installed
[Nav2 1.3.13 controller](https://github.com/ros-navigation/navigation2/blob/1.3.13/nav2_controller/src/controller_server.cpp)
resets its goal checker when it accepts a new path. The
[default tree](https://github.com/ros-navigation/navigation2/blob/1.3.13/nav2_bt_navigator/behavior_trees/navigate_to_pose_w_replanning_and_recovery.xml)
periodically replans at 1 Hz. This can interrupt stateful arrival capture during
the final turn; it is a source-based explanation to test, not a proven cause of
every observed failure.

The workflow selects the exact installed
[`navigate_w_recovery_and_replanning_only_if_path_becomes_invalid.xml`](https://github.com/ros-navigation/navigation2/blob/1.3.13/nav2_bt_navigator/behavior_trees/navigate_w_recovery_and_replanning_only_if_path_becomes_invalid.xml).
It keeps recovery behavior and computes a replacement path for a changed goal
or invalid current path. Its planning branch still checks at 1 Hz, but does
not unconditionally replace a valid path. This experiment targets the fixed
static depot route.

Copy the installed XML outside the checkout before warmup and freeze its
absolute path in `bt_navigator.ros__parameters.default_nav_to_pose_bt_xml` in
the SUT YAML. The adapter verifies that string parameter and the actual XML
digest before and after navigation. The tree is an invariant target asset;
changed or missing read-back/file evidence prevents admission. Keep the
selected XML unchanged and change only `vx_max` for the candidate.

The first fixed-BT cohort passed all twenty baseline gates and both controls;
the speed candidate produced a sole duration finding of +110.155%. Its independent
same-head repetition passed every route, but baseline-2 to baseline-5 increased
final distance by 0.121618 m against the unchanged 0.1 m allowance. Only 19 of 20
gates passed, so that repetition correctly stopped before control or candidate
collection. Conditional replanning did not establish stable final-distance gates.
The [runbook](../../docs/validation/runtime-acceptance.md) records exact artifacts,
read-back and digests, and preserves all earlier positive and negative cohorts.

## Next structural experiment: RotationShim

The exact
[Nav2 1.3.13 RotationShim source](https://github.com/ros-navigation/navigation2/blob/1.3.13/nav2_rotation_shim_controller/src/nav2_rotation_shim_controller.cpp)
configures MPPI under the same plugin namespace. With goal-heading rotation
enabled, it reads the goal checker's XY tolerance and, after position capture,
returns a rotation command with zero linear fields. Angular acceleration and
collision checks still apply; a failed rotation branch can fall back to MPPI.
This targets translation during the final turn, without guaranteeing zero
physical drift or stable gates.

Keep the conditional-replanning XML, stateful 0.20 m / 0.25 rad goal checker,
and other MPPI parameters unchanged. Only the wrapper/primary selection,
goal-heading flag, and final-heading activation listed above define the new
setup. The candidate still changes only `vx_max` from 0.5 to 0.2 m/s. Scenario
goal tolerance remains 0.35 m and default comparison gates remain 10% for
duration/path, 0.1 m for distance increase, and zero additional event counts.

This hypothesis requires a fresh warmup, five baselines, all twenty comparisons,
preselected baseline-1 capture, held-out control, candidate, and restored control,
then an independent fresh repetition of the frozen setup. Both series are
pending. No failed or successful earlier run supplies a baseline for this setup,
and no threshold is relaxed after seeing the results.

## Inspect the evidence

Download its artifact to inspect `experiment.json`, scenario results, observed
replays, target manifests, logs, and JSON/Markdown/JUnit comparison reports.
The artifact records failed attempts as well as completed measurements.
`COMPLETED_WITHOUT_DETECTED_SLOWDOWN` means the completed gate did not establish
the intended duration regression. It is not rewritten as success.

## Adapter contract

The checked-in [adapter](../../scripts/run_gazebo_attempt.sh) starts a new Gazebo
world and transport partition for every invocation. It renders the world before
launch, uses headless software rendering, explicitly creates the physical robot,
and verifies the model's observed Gazebo pose separately from AMCL localization.
Clock, scan, odometry, map clearance, TF, active Nav2 lifecycle nodes and the
navigation action must be ready before a goal is dispatched.

The adapter reads the absolute `ROBOTCI_GAZEBO_PARAMS_FILE` selected by the
experiment. Optional absolute launch, map and world selections use
`ROBOTCI_GAZEBO_LAUNCH_FILE`, `ROBOTCI_GAZEBO_MAP_FILE` and
`ROBOTCI_GAZEBO_WORLD_FILE`. Controller settings and the selected navigation XML
are read back before and after navigation; asset digests and process cleanup are
recorded in the scenario's
`.gazebo.json` sidecar. This example uses the root ROS namespace.

For manual execution, reproduce the workflow's target preparation first, then
run [gazebo_acceptance.py](../../scripts/gazebo_acceptance.py) with that frozen
controller file. Keep target inputs outside the RobotCI source tree and use a
new evidence directory for each experiment.

See the [acceptance runbook](../../docs/validation/runtime-acceptance.md) for the
measurement boundary and evidence requirements. General namespaced Nav2 probes
are supported, but this example does not verify a namespaced Clearpath simulator.
