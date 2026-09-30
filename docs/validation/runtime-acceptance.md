# Native Nav2 / Gazebo runtime acceptance

Status on 2026-09-30: the complete internal regression-detection experiment is
verified on the recorded Nav2/Gazebo setup. Five unchanged runs passed every
ordered-pair comparison, both unchanged controls passed, and the real controller
speed intervention produced a duration regression. Earlier failed calibration
attempts are retained below. This is evidence for one recorded setup and cohort,
not a broad simulator or statistical false-positive guarantee. The
maintenance environment is Ubuntu 24.04 with Python 3.12, but has no `ros2`,
`gz`, Docker executable, or `/opt/ros/jazzy/setup.bash`. Unit tests and the
existing Loopback CI alone are not evidence that this Gazebo integration works.
This experiment contributes zero external participants to M8.

## Checked-in experiment

The [Gazebo example](../../examples/nav2-gazebo/README.md),
[fresh-world adapter](../../scripts/run_gazebo_attempt.sh),
[readiness probe](../../robotci/ros/gazebo_readiness.py), and
[acceptance driver](../../scripts/gazebo_acceptance.py) implement this sequence.
The [Gazebo Acceptance workflow](../../.github/workflows/gazebo-acceptance.yml)
provisions an isolated Ubuntu runner and retains measurements, manifests, logs
and comparison artifacts even on failure. It selects command-velocity message
type from the installed TurtleBot bridge before freezing the baseline setup.

Target launch/controller files are kept outside the RobotCI source tree.
Otherwise a Python launch file can make an output directory an importable
namespace whose changing contents alter the harness fingerprint. The source
identity contract is preserved; target/controller bytes are recorded separately.
Every invocation uses a new world/transport partition and verifies physical
Gazebo pose separately from the localized pose. Controller settings are read
back before and after navigation, and cleanup must be confirmed before the run
is admitted into the comparison series.

## Observed first experiment: unchanged baselines were unstable

The real [Gazebo CI run 36732478638](https://github.com/Evolut10n11/robotci/actions/runs/36732478638),
at revision `19506bb4`, completed the warmup and all five baseline navigations
with `PASS`. Retained artifact `11105484556` contains the original controller
YAML, per-run results/replays/read-back, logs, and all 20 ordered-pair gates.
There were no observed stuck events or recoveries in those five baselines.

| Unchanged run | Duration, seconds | Path length, metres | Final goal distance, metres |
| --- | ---: | ---: | ---: |
| baseline-1 | 15.193 | 5.327 | 0.185 |
| baseline-2 | 13.301 | 5.089 | 0.305 |
| baseline-3 | 14.588 | 5.299 | 0.234 |
| baseline-4 | 15.193 | 5.355 | 0.190 |
| baseline-5 | 16.193 | 5.448 | 0.292 |

Eight of the 20 unchanged-pair comparisons produced `REGRESSION`: four exceeded
the default 10% duration allowance and four exceeded the default 0.1 m goal
distance allowance. The duration range was 21.7% relative to the shortest run;
goal distance varied by approximately 0.120 m. The driver stopped with
`UNCHANGED_BASELINES_UNSTABLE`. It did not capture a known-good baseline or run
the held-out control, speed intervention, or restored control. Navigation
success therefore did not establish usable regression detection for this setup.

The original installed controller enabled MPPI trajectory visualization and
noise regeneration, and used a stateful goal checker with 0.25 m XY and
0.25 rad yaw tolerances. Replay shows the first four runs reaching x=4 m in
11.190–11.596 seconds, while final completion varies more; the final poses are
consistent with a broad arrival criterion and a variable completion tail.
The logs contain no missed-controller-loop warnings. These observations support
testing a more precise, less costly controller preset; they do not prove that
one setting explains every source of variance.

For the second attempt, the workflow froze these settings before warmup in the
explicit SUT controller YAML:

| Setting | Frozen value |
| --- | --- |
| `FollowPath.visualize` | `false` |
| `FollowPath.regenerate_noises` | `false` |
| `general_goal_checker.xy_goal_tolerance` | `0.05` m |
| `general_goal_checker.yaw_goal_tolerance` | `0.10` rad |
| `general_goal_checker.stateful` | `false` |

The preset removes visualization work and per-iteration noise-thread wakeups,
and requires the XY criterion to remain satisfied while checking yaw. It does
not make a general determinism guarantee for MPPI, AMCL, or shared-host timing.
Readiness and post-navigation probes must confirm the exact preset, alongside
the controller's effective speed and source digest. The speed intervention
still changes only `FollowPath.vx_max` from 0.5 to 0.2 m/s.

The first series remains a failed stability experiment. Its runs are not reused
or selected as a baseline. Every revised setup must repeat warmup, all five
baselines, all 20 stability gates, the held-out control, candidate, and restored
control. Default regression thresholds and the predeclared selection of run 1
remain unchanged.

## Observed second experiment: tight goal-checker warmup timed out

The next [Gazebo CI run 36736326803](https://github.com/Evolut10n11/robotci/actions/runs/36736326803)
used the 0.05 m / 0.10 rad non-stateful goal checker listed above. Retained
artifact `11107048798` records a warmup `TIMEOUT` after 120.023 seconds, with
six observed stuck events and ten recoveries. The final reported distance was
0.136 m; all 596 recorded pose samples were valid. The driver reported
`INCOMPLETE`, restored the original controller bytes, and collected no
baselines, controls, or candidate comparison.

Before the first stuck event at 20.875 seconds, the closest observed position
was 0.309 m from the goal at 15.036 seconds, with yaw error approximately
0.089 rad. Over the entire run, the minimum observed XY distance was 0.106 m
at 61.495 seconds, with yaw error approximately 0.520 rad. Among samples
satisfying the 0.10 rad yaw criterion, the closest XY distance was 0.126 m.
No recorded sample satisfied even a 0.10 m XY criterion. The tighter checker
therefore did not produce a usable completion condition for this controller.

Inspection of the installed
[Nav2 1.3.13 MPPI source](https://github.com/ros-navigation/navigation2/blob/1.3.13/nav2_mppi_controller/src/critics/goal_angle_critic.cpp)
and retained parameters shows `GoalAngleCritic` becoming active within 0.5 m
of the goal, with cost weight 3, while the goal-position critic has weight 5.
The early alignment objective is a plausible contributor to the observed
near-goal stall; changing the goal checker alone did not resolve it. The
experiment does not establish that this is the only cause.

## Observed third preset: two unchanged cohorts remained unstable

The third preset used 0.15 m XY tolerance, 0.25 rad yaw tolerance, a non-stateful
goal checker, and a final-heading activation distance of 0.15 m. Visualization
and per-iteration noise regeneration remained disabled. Two separate CI runs
tested this same preset on the Gazebo PR and the subsequent integration PR:

- [PR #93 run 36742707538](https://github.com/Evolut10n11/robotci/actions/runs/36742707538),
  artifact `11111976272`, recorded checkout revision `75846c8`.
- [PR #94 run 36742824636](https://github.com/Evolut10n11/robotci/actions/runs/36742824636),
  artifact `11111881793`, recorded checkout revision `39e35c5`.

Each cohort completed its warmup and all five unchanged routes with `PASS`.
Warmup durations were 17.558 and 16.566 seconds respectively. Each internally
comparable cohort produced 13 passing and seven regressing ordered-pair gates,
then stopped with `UNCHANGED_BASELINES_UNSTABLE`. Neither run selected a
known-good baseline or evaluated a held-out control, candidate, or restored
control. No comparison across these different checkout revisions was used.

| Unchanged run | PR #93 duration, seconds | Recoveries | PR #94 duration, seconds | Recoveries |
| --- | ---: | ---: | ---: | ---: |
| baseline-1 | 15.942 | 0 | 15.249 | 0 |
| baseline-2 | 16.737 | 0 | 15.715 | 0 |
| baseline-3 | 15.748 | 0 | 16.474 | 0 |
| baseline-4 | 62.938 | 5 | 48.998 | 4 |
| baseline-5 | 43.849 | 3 | 42.127 | 3 |

The late two runs in both cohorts reached approximately 0.142–0.181 m from the
goal before their first recovery. At those closest pre-recovery samples, the
absolute yaw errors were approximately 0.464–1.037 rad. Their traces then show
near-goal turning, positional drift, and recovery cycles. This pattern supports
testing a completion protocol that can capture arrival before the final turn;
it does not establish a stable comparison result for that protocol.

## Current frozen preset: verified on the recorded setup

The successful full series kept visualization and per-iteration noise regeneration
disabled. It used a stateful goal checker with 0.20 m XY tolerance and the
original 0.25 rad yaw tolerance. The final-heading critic activates within
0.25 m, before the position capture boundary:

| Setting | Frozen value |
| --- | --- |
| `FollowPath.visualize` | `false` |
| `FollowPath.regenerate_noises` | `false` |
| `FollowPath.GoalAngleCritic.threshold_to_consider` | `0.25` m |
| `general_goal_checker.xy_goal_tolerance` | `0.20` m |
| `general_goal_checker.yaw_goal_tolerance` | `0.25` rad |
| `general_goal_checker.stateful` | `true` |

Inspection of the installed
[Nav2 1.3.13 SimpleGoalChecker](https://github.com/ros-navigation/navigation2/blob/1.3.13/nav2_controller/plugins/simple_goal_checker.cpp)
shows that stateful checking retains the satisfied XY criterion while checking
the final yaw. MPPI's final-heading critic is gated by position distance; the
0.25 m activation makes that objective available before the 0.20 m capture
boundary. The earlier pre-recovery arrivals motivated this fixed hypothesis.
The completed cohort below supports it on the recorded setup; it does not
establish reliability or bounded drift across other environments. RobotCI
still evaluates the observed final pose against the unchanged scenario policy.

The controller's XY completion tolerance remains stricter than its original
0.25 m. These are controller settings frozen before collecting new data;
RobotCI's task and comparison policy remain unchanged, including the default
10% duration/path and 0.1 m final-distance allowances. The adapter must read
back the complete preset before and after each navigation. Candidate YAML
changes only `FollowPath.vx_max` from 0.5 to 0.2 m/s.

All failed attempts and both third-preset cohorts remain evidence of setup
limitations. Their runs were not reused or handpicked as a known-good baseline.
The successful cohort used fresh measurements for the warmup, five unchanged
runs, all 20 ordered-pair gates, held-out control, candidate, and restored control.

## Completed internal cohort and regression proof

[Gazebo CI run 36749494953](https://github.com/Evolut10n11/robotci/actions/runs/36749494953)
completed successfully for PR head `c461b555`. Its retained
[artifact 11114463143](https://github.com/Evolut10n11/robotci/actions/runs/36749494953/artifacts/11114463143)
contains 145 files, including all nine navigation result/replay/target bundles,
20 stability gates, captured baseline, control/candidate/restored gate reports
in JSON/Markdown/JUnit, original/candidate YAML, package inventory, and logs.
The archive SHA256 is
`c6dc9edb37359980abaad3112f8f1944d6a2eebe8279aa4f9d84125b559b6a0a`.
The recorded checkout revision is `9cc8d1459973846f5b9547a46b497077ca3d7c73`;
the upstream launch remains pinned at
`645abd95f2be02a13ca539b29c2ddc065db34f89`. Installed package versions and
actual map/world/launch/TurtleBot/bridge/Fuel bytes are identified in the bundle.

| Run | MPPI speed cap, m/s | Duration, seconds | Path, metres | Final distance, metres | Feedback/replay samples |
| --- | ---: | ---: | ---: | ---: | ---: |
| warmup | 0.5 | 15.480 | 5.529 | 0.167 | 78 |
| baseline-1 | 0.5 | 14.921 | 5.432 | 0.152 | 75 |
| baseline-2 | 0.5 | 15.294 | 5.511 | 0.197 | 77 |
| baseline-3 | 0.5 | 14.320 | 5.379 | 0.216 | 72 |
| baseline-4 | 0.5 | 15.075 | 5.487 | 0.134 | 75 |
| baseline-5 | 0.5 | 15.289 | 5.451 | 0.155 | 77 |
| held-out control | 0.5 | 15.135 | 5.390 | 0.181 | 76 |
| candidate | 0.2 | 28.689 | 5.411 | 0.084 | 144 |
| restored control | 0.5 | 14.725 | 5.444 | 0.195 | 74 |

Every navigation completed with `PASS`, valid final pose, zero invalid pose
samples, and zero observed stuck events or recoveries. The five baseline
durations ranged from 14.320 to 15.294 seconds, with median 15.075 seconds;
the largest ordered-pair duration increase was 6.802%. Their final-distance
spread was 0.0823 m. All **20 of 20** separate directed stability gates passed
the unchanged default policy. Baseline run 1 was selected by the rule declared
before collection, not by post-candidate performance.

The held-out and restored controls passed with no regression findings. The
candidate changed only `controller_server.ros__parameters.FollowPath.vx_max`
from 0.5 to 0.2 m/s. Its gate reported exactly one finding: navigation duration
increased from 14.921 to 28.689 seconds, **+92.273%**, exceeding the unchanged
10% allowance. Path length, final distance, recoveries, and stuck counters did
not produce regression findings. The experiment status is
`COMPLETED_DURATION_REGRESSION`.

Every `results/depot_route.gazebo.json` records physical start, map clearance,
progressing clock, sensors, required TF, active Nav2/action endpoint, command
type, and fixed-preset verification. Controller and preset read-back were
stable before and after each navigation. Baseline/control/restored runs read
back 0.5 m/s and the candidate read back 0.2 m/s. All nine runs used different
Gazebo transport partitions. Each cleanup record reports both
`process_groups_stopped=true` and `owned_processes_stopped=true`, with an empty
survivor list. These are observations of the adapter's owned processes, not an
unrestricted claim about unrelated host processes.

The comparable suites share execution fingerprint
`sha256:0db5f99a76acd97085f51fadbb7febc6463e5fbf2e160c3e6f8391e90106576f`.
SUT digests are recorded separately:

- original/restored controller:
  `sha256:9a66eefe15a5aec140ecf3d910e131ee193d8850d26e0ab2137385cecc4af26d`;
- speed-intervention controller:
  `sha256:3833afe0515b07b8f5b79c297dd281a30c86a610a21307c8128ae82a6b217e16`.

Before/after read-back digests match the corresponding subject bytes, and
`experiment.json` records `subject_restored=true`. Thus the slower candidate
was evaluated under the same harness and task, with passing controls and
restoration evidence. This completes the internal experiment on this pinned
configuration. It contributes **zero external teams** to M8; an independent
team's reproduction and broader environment validation remain separate work.

## Target and experiment boundary

Use the official Nav2 TurtleBot 4 Gazebo demo first, in an isolated Ubuntu
24.04 / ROS 2 Jazzy simulation workspace. Its empty ROS namespace keeps this
cohort separate from the Clearpath integration described in
[clearpath-preflight.md](clearpath-preflight.md). Namespace support is implemented;
execution against the actual Clearpath project has not been verified.

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

Verify the checked-in adapter or the target-specific equivalent on the
provisioned host before calling the manual commands below. The automated driver
performs the complete measurement series and reports incomplete or unstable
experiments explicitly; code being present alone is not runtime evidence.
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
