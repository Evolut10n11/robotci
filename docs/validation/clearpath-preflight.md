# Clearpath internal preflight — 2026-09-21

Outcome: onboarding/config selection verified; simulation and baseline comparison
not run. This is a RobotCI-maintainer preflight on a public checkout, not a pilot
performed or endorsed by Clearpath. It contributes zero external-team results.
No outreach or changes to the upstream repository were sent.

## Revisions and environment

- RobotCI: public-alpha main `12ca1a3a20282741bc38cd6b27cc08e6870460ed`,
  version `0.1.0a1`; editable installation in an isolated Python 3.12.14 venv.
- Target: [`clearpathrobotics/clearpath_nav2_demos`](https://github.com/clearpathrobotics/clearpath_nav2_demos/tree/ef39aacebd918b7cbf0ca6cdf2e74644a0d240ba),
  branch `jazzy`, revision `ef39aacebd918b7cbf0ca6cdf2e74644a0d240ba`, package `2.8.1`.
- Separate target checkout; commands ran from its directory with an absolute
  target configuration path. No RobotCI runtime adapter was configured.
- Linux execution environment; no `ros2`, no `/opt/ros`, no Docker executable.

## Observed checks

| Check | Exit | Observation |
| --- | ---: | --- |
| `robotci-init` in target checkout | 0 | Created only the starter `smoke_route` configuration in that checkout |
| `robotci validate --config` with the absolute target path | 0 | Validated the target's single scenario, not RobotCI's three demo routes |
| `robotci plan --config` with the same target path | 0 | Resolved that same scenario and reported that no runtime was started |
| `robotci-doctor --require-ros` | 1 | `status=FAIL`, selected runtime `none`; native ROS2 Jazzy/Nav2 unavailable |
| Real Clearpath suite, baseline capture, candidate gate | not run | Blocked before simulation setup |

The starter still uses `map_id: nav2-loopback` and generic coordinates. These were
not treated as a Clearpath warehouse route. Validation proves configuration and
project selection only; it does not prove a safe route or simulator compatibility.
The missing runtime is a limitation of this execution environment, not evidence
of a Clearpath or RobotCI behavior defect.

## Source findings that change the next experiment

1. This repository does not launch a robot or simulator. Its
   [README](https://github.com/clearpathrobotics/clearpath_nav2_demos/blob/ef39aacebd918b7cbf0ca6cdf2e74644a0d240ba/README.md)
   requires a running `clearpath_robot` or `clearpath_simulator` before localization
   and navigation. For this pilot use simulation only. Starting `nav2.launch.py`
   alone cannot establish a complete experiment.
2. The
   [navigation launch](https://github.com/clearpathrobotics/clearpath_nav2_demos/blob/ef39aacebd918b7cbf0ca6cdf2e74644a0d240ba/launch/nav2.launch.py)
   reads `robot.yaml` under `setup_path`, derives the platform and namespace,
   namespaces Nav2, and remaps TF and odometry. Its default simulation-time flag
   is false. The adapter must explicitly select simulation time and discover the
   actual namespaced action endpoint; assuming global `/navigate_to_pose` is wrong
   for a nonempty robot namespace.
3. RobotCI's preflight-era
   [navigation probe](https://github.com/Evolut10n11/robotci/blob/12ca1a3a20282741bc38cd6b27cc08e6870460ed/robotci/ros/navigation_scenario.py)
   constructs `BasicNavigator` without a namespace and initializes rclpy with a
   fixed argument list. It does not expose a namespace/remapping CLI option.
   Therefore the documented adapter seam alone was not evidence that namespaced
   Clearpath navigation works. The namespace integration below removes the probe
   interface gap, but it still needs verification on the target runtime before
   claiming compatibility.

## Namespace integration — 2026-09-30

The native probe now accepts `ROBOTCI_ROS_NAMESPACE`, or a direct `--namespace`
argument. Jazzy's [BasicNavigator API](https://api.nav2.org/nav2-jazzy/html/robot__navigator_8py_source.html)
accepts that namespace and creates a relative `navigate_to_pose` action client.
Set the namespace from the simulator's actual `robot.yaml` before starting the
RobotCI suite; do not guess it from the platform model:

```bash
export ROBOTCI_ROS_NAMESPACE="/a200"
robotci run --runtime native --config "$PWD/robotci.yaml"
```

This example assumes the verified setup uses `/a200`; substitute the concrete
namespace selected by that setup. The external attempt script still launches
or connects to the namespaced stack. The built-in Loopback launch remains in
the root namespace.

After its readiness/reset checks, an attempt script may invoke the probe with
the explicit CLI argument and the inherited scenario contract:

```bash
"$ROBOTCI_PYTHON" -m robotci.ros.navigation_scenario \
  --namespace "$ROBOTCI_ROS_NAMESPACE" \
  --scenario "$ROBOTCI_SCENARIO" \
  --start-x "$ROBOTCI_START_X" --start-y "$ROBOTCI_START_Y" \
  --start-yaw "$ROBOTCI_START_YAW" \
  --goal-x "$ROBOTCI_GOAL_X" --goal-y "$ROBOTCI_GOAL_Y" \
  --goal-yaw "$ROBOTCI_GOAL_YAW" \
  --map-id "$ROBOTCI_MAP_ID" \
  --output "$ROBOTCI_RESULT_FILE" \
  --timeout-sec "$ROBOTCI_TIMEOUT_SEC" \
  --goal-tolerance-m "$ROBOTCI_GOAL_TOLERANCE_M" \
  --min-feedback-samples "$ROBOTCI_MIN_FEEDBACK_SAMPLES"
```

`--namespace` overrides the inherited setting for a direct probe invocation.
For a suite, keep it consistent with the namespace set before `robotci run`
so execution and the captured environment describe the same ROS graph.

Empty namespace and `/` select the root graph. Relative names such as `a200`
normalize to `/a200`; malformed namespaces fail before ROS initialization.
Native execution admits the canonical namespace and hashes it into runtime
provenance. Equivalent root settings retain the default identity, while changing
the robot namespace makes baseline and candidate incompatible.

The probe waits at most 30 seconds for that namespace's NavigateToPose server
before dispatching a goal. A missing or wrong namespace produces exit `3`,
`INFRA_ERROR`, and `reason_code: navigation_server_unavailable`. If the server
disappears after this check, the outer runtime watchdog still bounds the attempt.
Unit tests cover root behavior, canonicalization, explicit override, final pose
feedback, unavailable-server evidence, and namespace-sensitive fingerprints.

A ROS namespace changes action/topic names, not TF frame identifiers. The probe
continues to use the `map` frame. The adapter must verify the target map frame,
localization, TF/topic remapping, and start pose independently. Arbitrary ROS
remapping and a configurable map frame are not exposed by this slice.
No Clearpath simulator was executed as part of these namespace unit checks;
the real namespaced success and wrong-namespace acceptance checks remain pending.

## Next runnable acceptance sequence

Use an Ubuntu 24.04 environment with ROS2 Jazzy and the Clearpath simulation
dependencies. Do not launch any physical robot. Pin both the simulator and this
navigation demo revision before collecting comparable results.

1. Start an `a200` simulated robot in the warehouse world with a concrete
   `robot.yaml`, simulation clock, sensor topics, and TF tree.
2. Start warehouse localization and navigation with `use_sim_time:=true` and the
   same setup directory; verify the actual namespace, action, and lifecycle state.
3. Set the implemented probe namespace and resolve target-specific TF/topic
   remappings. Verify both namespace success
   and wrong-namespace failure with bounded waits; include effective settings in
   runtime provenance.
4. Choose a verified free-space route, set its start/goal and real map identity,
   and explicitly reset/localize the simulated robot at that start before each
   attempt. A probe's `--start-*` metadata does not reset a robot.
5. Run through a small native adapter with fresh logs and repeatable cleanup,
   then inspect result schema, telemetry quality, goal tolerance, and suite
   provenance before saving a baseline.
6. Run a comparable real Nav2 configuration change without changing the task or
   execution profile. Record the observed gate verdict, not an expected verdict.
7. Review repeatability and the report before inviting a participant to reproduce
   it. Internal success still does not count toward the five-team cohort.

The next technical blocker is access to that simulation environment and
verification of its namespace/frame integration. Paid interest and repeat-use intent remain
unknown until an external team actually tries the workflow and answers.
