# Nav2 / Gazebo controller acceptance

This example runs a real TurtleBot 4 in Gazebo Harmonic with ROS 2 Jazzy on
Ubuntu 24.04. The route is checked against the depot occupancy map before
navigation. It is an internal integration experiment, not an external M8 pilot.

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

Before warm-up, the workflow freezes the same benchmark preset for every run:

| Nav2 setting | Value |
| --- | --- |
| `FollowPath.visualize` | `false` |
| `FollowPath.regenerate_noises` | `false` |
| `general_goal_checker.stateful` | `true` |
| `general_goal_checker.xy_goal_tolerance` | `0.20 m` |
| `general_goal_checker.yaw_goal_tolerance` | `0.25 rad` |
| `FollowPath.GoalAngleCritic.threshold_to_consider` | `0.25 m` |

This disables trajectory visualization and repeated noise generation, uses
Nav2's position latch before final orientation, and activates final-heading cost
slightly before position capture. These settings are a calibration hypothesis.
The adapter verifies the actual parameter values before and after navigation.
Controller frequency remains `20 Hz`, batch size remains `2000`, and the
intervention changes only `vx_max`. This preset does not guarantee deterministic
navigation; the five unchanged baselines must still pass all default gates.
The runbook preserves the unstable upstream baseline experiment, the 0.05 m
goal-checker warmup timeout, and both unstable 0.15 m simultaneous-check series.
The new preset requires fresh runtime measurements; no failed series supplies
a known-good baseline.

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
`ROBOTCI_GAZEBO_WORLD_FILE`. Controller settings are read back before and after
navigation; asset digests and process cleanup are recorded in the scenario's
`.gazebo.json` sidecar. This example uses the root ROS namespace.

For manual execution, reproduce the workflow's target preparation first, then
run [gazebo_acceptance.py](../../scripts/gazebo_acceptance.py) with that frozen
controller file. Keep target inputs outside the RobotCI source tree and use a
new evidence directory for each experiment.

See the [acceptance runbook](../../docs/validation/runtime-acceptance.md) for the
measurement boundary and evidence requirements. General namespaced Nav2 probes
are supported, but this example does not verify a namespaced Clearpath simulator.
