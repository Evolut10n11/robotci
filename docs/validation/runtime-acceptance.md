# Native Nav2 / Gazebo runtime acceptance

Status on 2026-09-30: the first complete cohort using the installed Nav2 1.3.13
conditional-replanning behavior tree detected the real speed intervention, but
its independent same-head repetition failed one unchanged final-distance gate.
Timing was stable and all six repeated routes passed without recoveries or stuck
events; the driver still correctly stopped before control or candidate collection.
Repeatable acceptance under the default policy is **not established**. The first
RotationShim warmup then failed navigation despite verified setup and cleanup.
The next fixed experiment keeps that controller and selects `map` as the local
costmap frame; its full series and independent repetition remain pending.
All positive and negative outcomes,
including earlier failed calibrations, are retained below. No
simulator-wide or statistical false-positive guarantee is claimed. The
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

## Controller preset: one successful cohort, repeat validation failed

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
One completed cohort below supports it for that particular experiment, but the
subsequent unchanged repetition was unstable. It does not establish repeatable
completion, bounded drift, or reliable gates for the preset. RobotCI still
evaluates the observed final pose against the unchanged scenario policy.

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

## Historical completed cohort and regression proof

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
restoration evidence. That run completed one internal experiment on the recorded
configuration. The later failed repetition below prevents treating this as
reproducibly validated acceptance. It contributes **zero external teams** to M8;
an independent team's reproduction and broader validation remain separate work.

## Previous repetition: unchanged baseline stability failed

[Gazebo CI run 36752331669](https://github.com/Evolut10n11/robotci/actions/runs/36752331669)
for PR head `b8addf5b` attempted a fresh complete measurement series with the
same frozen controller preset. Retained
[artifact 11116210736](https://github.com/Evolut10n11/robotci/actions/runs/36752331669/artifacts/11116210736)
records checkout revision `c778b1eb60dbbee8140579b47f718e1b831efc53`.
Warmup and all five unchanged navigation runs finished with `PASS`, but the
third baseline required five recoveries and produced two stuck events.

| Run | Duration, seconds | Path, metres | Final distance, metres | Recoveries | Stuck events |
| --- | ---: | ---: | ---: | ---: | ---: |
| warmup | 15.787 | 5.452 | 0.153 | 0 | 0 |
| baseline-1 | 17.143 | 5.535 | 0.252 | 0 | 0 |
| baseline-2 | 16.196 | 5.423 | 0.112 | 0 | 0 |
| baseline-3 | 61.036 | 6.176 | 0.031 | 5 | 2 |
| baseline-4 | 16.049 | 5.295 | 0.155 | 0 | 0 |
| baseline-5 | 16.563 | 5.443 | 0.134 | 0 | 0 |

Only 11 of 20 directed unchanged-baseline gates passed; nine reported
`REGRESSION`. Comparisons against baseline-3 identified additional duration,
path, stuck events, and recoveries. Other comparisons also exceeded the
unchanged 0.1 m final-distance allowance; for example baseline-2 to baseline-1
increased final distance by approximately 0.140 m. The instability is therefore
not confined to one slow duration measurement.

The driver correctly stopped with `UNCHANGED_BASELINES_UNSTABLE`. It did not
capture a known-good baseline or execute the held-out control, speed candidate,
or restored-control navigation. `subject_restored=true` records restoration of
the source controller bytes; it does not imply that a restored-control run was
performed. Read-back confirmed the fixed preset and 0.5 m/s speed before and
after each of the six navigations. Their target checks and owned-process cleanup
records passed with no survivors.

All six suites are internally comparable under execution fingerprint
`sha256:a4e0df18181be5ed6a03a63f2d078e38972f450fa10679d09d81fd851c43dc40`.
The original/controller digest remained
`sha256:9a66eefe15a5aec140ecf3d910e131ee193d8850d26e0ab2137385cecc4af26d`.
This failed and the historical successful cohort have different execution
fingerprints; no cross-cohort gate or rewritten fingerprint was used.

The earlier +92.273% candidate result remains a completed observation from its
own successful cohort. It is not a candidate result for this failed repetition,
and the failed unchanged series cannot be dropped or replaced by selected runs.
Further engineering and a fresh complete measurement series are required before
claiming repeatable acceptance. The default 10% duration/path, 0.1 m distance,
zero-additional-event policy and predeclared selection of baseline run 1 remain
unchanged. External M8 evidence remains zero.

## Fixed behavior-tree experiment and source-backed hypothesis

Inspection of installed Nav2 1.3.13 exposes a control-flow interaction worth
testing separately from controller tolerances. In
[ControllerServer](https://github.com/ros-navigation/navigation2/blob/1.3.13/nav2_controller/src/controller_server.cpp),
accepting a new `FollowPath` goal calls `setPlannerPath`, which resets the
selected goal checker. The
[default navigation tree](https://github.com/ros-navigation/navigation2/blob/1.3.13/nav2_bt_navigator/behavior_trees/navigate_to_pose_w_replanning_and_recovery.xml)
requests a global replan at 1 Hz. Thus periodic path updates can clear the
stateful arrival latch while the robot turns toward its final heading. This
source-backed mechanism is a hypothesis for the near-goal failures; the source
does not prove that it explains every unstable run.

The new series selects the exact installed tree
[`navigate_w_recovery_and_replanning_only_if_path_becomes_invalid.xml`](https://github.com/ros-navigation/navigation2/blob/1.3.13/nav2_bt_navigator/behavior_trees/navigate_w_recovery_and_replanning_only_if_path_becomes_invalid.xml).
It retains planning, control, and system recovery branches. Its 1 Hz planning
branch checks for a changed goal or invalid existing path before computing a
replacement, rather than unconditionally replacing a valid path each second.
An initial path is still computed, and an invalid path or changed goal still
triggers replanning. The experiment is scoped to this fixed static depot route;
it is not a recommendation for arbitrary dynamic environments.

Before warmup, the workflow copies the installed XML outside the checkout and
sets `bt_navigator.ros__parameters.default_nav_to_pose_bt_xml` in the explicit
SUT YAML to that stable absolute path. Installed ROS resources are not patched.
The copied XML is frozen for the complete series and identified by content
digest. The adapter must verify the actual typed string parameter before and
after each navigation, verify the selected file's digest, and include the XML
among the invariant target assets. Missing, changed, or inconsistent tree
provenance rejects the run instead of admitting it into the comparison series.

The controller preset remains unchanged: visualization and noise regeneration
disabled, stateful XY capture at 0.20 m, yaw tolerance 0.25 rad, and final-heading
activation at 0.25 m. All runs use the same frozen XML. The candidate still
changes only `FollowPath.vx_max` from 0.5 to 0.2 m/s. RobotCI's scenario, 10%
duration/path allowance, 0.1 m distance allowance, and zero additional event
allowance remain unchanged.

This tree selection is an experiment setup change. Its first complete cohort
and failed independent same-head repetition are recorded below. No earlier run
is reused, discarded, or promoted to establish it. Each
cohort must independently complete warmup, all five unchanged baselines, all
20 ordered-pair gates, the preselected baseline-1 capture, held-out control,
real speed candidate, and restored control. The previous successful and failed
cohorts remain separate observations, and external M8 participation remains zero.

## First fixed-BT cohort: completed regression proof

[Gazebo CI run 36755699992](https://github.com/Evolut10n11/robotci/actions/runs/36755699992),
attempt 1, [job 110025258065](https://github.com/Evolut10n11/robotci/actions/runs/36755699992/job/110025258065),
completed the full experiment for PR head
`1dd20a71c477602ca099f1bb41b361fe80d51426`. The recorded checkout merge is
`004ae02b45b411b9a1abcd8fe181321f1832ee99`. Retained
[artifact 11116907304](https://github.com/Evolut10n11/robotci/actions/runs/36755699992/artifacts/11116907304)
contains 146 files: the nine result/replay/target bundles, all 20 directed
stability gates, captured baseline, control/candidate/restored JSON/Markdown/JUnit gates, frozen
behavior-tree XML, subject YAML, package inventory, and logs. Its archive SHA256
is `c1cd39f4a84da4b883b54a01bfc5afcb0d9e4a4e949c07cc4426c4d692cde0dc`.

| Run | MPPI speed cap, m/s | Duration, seconds | Path, metres | Final distance, metres | Feedback/replay samples |
| --- | ---: | ---: | ---: | ---: | ---: |
| warmup | 0.5 | 13.123 | 5.257 | 0.109 | 66 |
| baseline-1 | 0.5 | 12.929 | 5.266 | 0.123 | 65 |
| baseline-2 | 0.5 | 13.476 | 5.305 | 0.107 | 68 |
| baseline-3 | 0.5 | 13.079 | 5.210 | 0.110 | 66 |
| baseline-4 | 0.5 | 12.577 | 5.137 | 0.188 | 63 |
| baseline-5 | 0.5 | 12.888 | 5.184 | 0.174 | 65 |
| held-out control | 0.5 | 13.678 | 5.314 | 0.080 | 69 |
| candidate | 0.2 | 27.171 | 5.251 | 0.102 | 136 |
| restored control | 0.5 | 14.055 | 5.406 | 0.149 | 71 |

All nine navigations completed with `PASS`, complete evidence/provenance, valid
final poses, zero invalid pose samples, and zero observed recoveries or stuck
events. Received, valid, and replay sample counts agree. Independently loading
the suites, results, and replays with the core and recomputing every gate
confirmed **20 of 20** directed baseline comparisons passing the unchanged
policy. Baseline durations ranged from 12.577 to 13.476 seconds, with median
12.929 seconds; the largest ordered-pair increase was 7.148%. Their final-distance
spread was 0.08065 m. Baseline run 1 was selected by the predeclared rule.

Both held-out and restored controls passed with no findings. The candidate
changed only `FollowPath.vx_max` from 0.5 to 0.2 m/s and produced exactly one
finding: duration increased from 12.929 to 27.171 seconds, **+110.155%**, against
the unchanged 10% allowance. Path, final distance, recoveries, and stuck counts
did not produce findings. The driver reported `COMPLETED_DURATION_REGRESSION`
and `subject_restored=true`; the restored-control navigation was actually
performed and passed.

Every target manifest passed strict admission. The actual typed
`default_nav_to_pose_bt_xml` parameter before and after navigation matched the
expected canonical path
`/home/runner/work/_temp/robotci-gazebo-target/navigation.xml`. The copied XML,
archived XML, before/after file records, and invariant target asset all have
SHA256 `684c368fff80558623adc50c59d6f4f8f09a6fbc9138fa70cad32ffda03333b4`.
The complete controller preset, target assets, and effective controller read-back
remained stable: 0.5 m/s for unchanged/restored runs and 0.2 m/s for the candidate.
All nine runs used distinct transport partitions; each cleanup confirmed both
owned-process and process-group termination, with no survivors.

The suites share execution fingerprint
`sha256:bbd273c44f68ce3d6622abd7a8f7408937aa5120f2d7799a17649573b032dbe6`.
Actual original/restored subject bytes match
`sha256:77542cf7366ed509bda86f53032b9a90d642d63b9e80ffbb03b117cd0d8168c2`;
candidate bytes match
`sha256:f832436489ba7b7fdbeef22c47ff870ff6790f51fa79b72e1f1399782a93646b`.
The XML selection is unchanged throughout this cohort, and the controller's
single speed delta remains separate from the stable harness identity.

Each of the nine Nav2 logs contains exactly one navigation-goal receipt and one
completion, zero `Passing new path to controller` updates, and zero progress
failures. There are also zero path updates in the final five seconds. These
observations are consistent with retaining the stateful arrival latch instead
of resetting it through periodic valid-path replacement. They support the
source-backed mechanism on this controlled static route, without establishing
that it is the sole cause of every earlier failure.

This is one completed internal regression-detection experiment for the fixed
BT setup. Attempt 2 on the exact same PR head used an independent fresh job
with no code or parameter changes between cohorts, but failed unchanged baseline
stability as recorded below. The first success does not replace that failure,
establish repeatable acceptance or a statistical false-positive bound, or
contribute an external participant to M8.

## Fixed-BT repetition: final-distance stability failed

Attempt 2 of [run 36755699992](https://github.com/Evolut10n11/robotci/actions/runs/36755699992),
[job 110033236297](https://github.com/Evolut10n11/robotci/actions/runs/36755699992/job/110033236297),
used the exact same PR head `1dd20a71c477602ca099f1bb41b361fe80d51426` and
checkout merge `004ae02b45b411b9a1abcd8fe181321f1832ee99` as attempt 1.
Retained [artifact 11117198608](https://github.com/Evolut10n11/robotci/actions/runs/36755699992/artifacts/11117198608)
contains 112 files and has archive SHA256
`a21dc1447df7461f5269acb2ff08dad221e868a13515942dee9818e0b24526e1`.

| Run | Duration, seconds | Path, metres | Final distance, metres | Feedback/replay samples |
| --- | ---: | ---: | ---: | ---: |
| warmup | 14.708 | 5.369 | 0.128878 | 73 |
| baseline-1 | 14.592 | 5.380 | 0.123301 | 73 |
| baseline-2 | 13.706 | 5.311 | 0.071493 | 69 |
| baseline-3 | 14.209 | 5.370 | 0.133556 | 71 |
| baseline-4 | 14.387 | 5.398 | 0.094472 | 72 |
| baseline-5 | 13.726 | 5.346 | 0.193111 | 68 |

All six navigations passed with complete evidence/provenance, valid final poses,
zero invalid samples, and zero recoveries or stuck events. Received, valid, and
replay sample counts agree. Baseline durations ranged from 13.706 to 14.592
seconds, with median 14.209 seconds and maximum ordered-pair increase of 6.464%.
The independent core recomputation confirmed **19 of 20** gates passing and one
`REGRESSION`: baseline-2 to baseline-5 increased final distance from
0.07149325996349674 to 0.19311079407079682 m, a 0.12161753410730007 m increase
against the unchanged 0.1 m allowance. No duration, path, or event finding was
reported. Navigation success and stable timing did not establish stable gates.

The driver reported `UNCHANGED_BASELINES_UNSTABLE`. It did not capture a baseline
or run the held-out control, candidate, or restored-control navigation.
`subject_restored=true` confirms restoration of the original subject bytes,
not a performed restored-control run. The earlier +110.155% speed result belongs
only to attempt 1 and is not a candidate observation for this failed repetition.

Target assets, subject bytes, policy, execution fingerprint
`sha256:bbd273c44f68ce3d6622abd7a8f7408937aa5120f2d7799a17649573b032dbe6`,
and environment fingerprint
`sha256:830594ce303f471c4f0f06be3deceea8db851aa121cea284c1dceb06dd060c29`
match attempt 1 exactly. All six manifests passed strict admission, with expected,
before, and after BT/controller/preset records agreeing: MPPI at 0.5 m/s,
stateful 0.20 m / 0.25 rad checking, and final-heading activation at 0.25 m.
The archived XML has
the same `684c368fff80558623adc50c59d6f4f8f09a6fbc9138fa70cad32ffda03333b4`
digest. Each run used a different transport partition and confirmed both cleanup
flags with no survivors. All six Nav2 logs contain one goal receipt and one
completion, zero new-path updates, zero progress errors, and zero missed-rate
warnings. The conditional-replanning change eliminated observed path replacement
in these cohorts, but did not eliminate final-distance variation.

## RotationShim experiment and source-backed hypothesis

The RotationShim setup addresses final translation during yaw alignment rather
than changing RobotCI's comparison allowances. The exact installed
[Nav2 1.3.13 RotationShim source](https://github.com/ros-navigation/navigation2/blob/1.3.13/nav2_rotation_shim_controller/src/nav2_rotation_shim_controller.cpp)
configures its primary controller with the same plugin name and parameter
namespace. With `rotate_to_goal_heading=true`, it obtains the XY tolerance from
the selected goal checker. After its position checker captures arrival, the
goal-heading branch returns a rotation command whose linear fields are zero.
Its angular command remains subject to acceleration limits and collision checks.
If the rotation branch cannot produce a valid command, the code can fall back
to the primary controller; zero commanded translation is not a guarantee of
zero observed physical drift.

The frozen setup changes are:

| Setting | Frozen value |
| --- | --- |
| `FollowPath.plugin` | `nav2_rotation_shim_controller::RotationShimController` |
| `FollowPath.primary_controller` | `nav2_mppi_controller::MPPIController` |
| `FollowPath.rotate_to_goal_heading` | `true` |
| `FollowPath.GoalAngleCritic.threshold_to_consider` | `0.20` m |

The MPPI primary controller remains in the same `FollowPath` namespace. Its
other parameters remain unchanged, including visualization/noise settings,
controller frequency, batch size, and the baseline 0.5 m/s speed cap. The goal
checker remains stateful with 0.20 m XY and 0.25 rad yaw tolerance. The final-heading
critic's 0.20 m activation now matches the XY capture boundary. The exact frozen
conditional-replanning XML remains the same invariant asset.

This source-backed hypothesis targets endpoint movement during final orientation
on the fixed static route. The previous distance failure does not prove that this
mechanism explains all variation; the first warmup below failed rather than
establishing successful collection. Typed before/after read-back must
confirm the wrapper plugin, primary controller, heading flag, complete preset,
and effective MPPI speed, together with unchanged BT and target provenance.

The candidate still changes only `FollowPath.vx_max` from 0.5 to 0.2 m/s.
Scenario goal tolerance stays 0.35 m; default gates remain 10% for duration/path,
0.1 m for final-distance increase, and zero additional stuck/recovery events.
Every revised setup must collect fresh measurements; no earlier run supplies a
new baseline, no failed run is discarded, and external M8 participation remains
zero.

## Observed RotationShim warmup: navigation failed

[Gazebo run 36761957082](https://github.com/Evolut10n11/robotci/actions/runs/36761957082),
attempt 1, [job 110046493181](https://github.com/Evolut10n11/robotci/actions/runs/36761957082/job/110046493181),
tested PR head `520c126f269807091d6036d69966e637b8cbdf65` at checkout merge
`36a7db79c01162ce61c8a0f273f22845a7f42f80`. Retained
[artifact 11118939322](https://github.com/Evolut10n11/robotci/actions/runs/36761957082/artifacts/11118939322)
contains 17 files and has archive SHA256
`7a78d5da3e8ac6a67859201c22714f65be272be97c51652d710ea3837040649e`.
Its original YAML used `odom` as the local costmap's global frame.

| Measurement | Warmup observation |
| --- | --- |
| Navigation result | `FAILED` |
| Duration | 43.324 seconds |
| Path length | 6.069056834523745 m |
| Final goal distance | 0.588347574265819 m |
| Recoveries / stuck events | 16 / 2 |
| Received / valid / replay samples | 216 / 216 / 216 |
| Invalid poses / final-pose valid | 0 / `true` |

The suite failed, and the driver reported `INCOMPLETE` with exit 3. Independent
core loading validated the failed suite, result, and matching replay as complete
evidence/provenance. Warmup was not admitted: `runs` and `unchanged_pair_gates` are
empty in the experiment manifest. No baseline, held-out control, speed candidate,
or restored-control navigation was executed. `subject_restored=true` records
source-byte restoration only. A candidate YAML with the sole `vx_max` change
was prepared; its existence is not an executed candidate observation.

All ten typed controller/preset fields passed before/after read-back, including
the RotationShim wrapper, MPPI primary, goal-heading flag, 0.5 m/s speed,
0.20 m heading activation, and stateful 0.20 m / 0.25 rad goal checking.
The navigation XML and target assets remained unchanged, with XML digest
`684c368fff80558623adc50c59d6f4f8f09a6fbc9138fa70cad32ffda03333b4`.
The original subject and before/after parameter digests match
`sha256:61444050c3026ced09abc56ed7f675983ee8afd74ebca6ba70f9cc2aab581582`.
Both owned-process and process-group cleanup passed with no survivors.
Verified setup and cleanup do not imply that the controller completed its task.

The warmup execution fingerprint is
`sha256:3699fef0f2d0079c3f4da5309ae9efb0ed6f9d9741fd73baecb62fc8be53851c`.
The first progress failure occurs at approximately 21.90 seconds. The zero-pose
plans and repeated recovery errors occur after that initial failure, so those
later planning errors do not explain its onset. Logs contain no RotationShim
fallback message or new-path update. The closest replay
sample is approximately 0.173787 m from the map-frame goal at 12.359 seconds,
with yaw error approximately -0.4863 rad. A later near-zero-yaw, stationary phase
remains approximately 0.2391 m from that goal. These observations motivate a
frame-consistency test; no retained TF time series establishes its physical cause.

## Next frame experiment: local costmap in map, verification pending

The exact [Nav2 1.3.13 ControllerServer](https://github.com/ros-navigation/navigation2/blob/1.3.13/nav2_controller/src/controller_server.cpp)
caches the path's final pose, including its original timestamp, in `setPlannerPath`.
`isGoalReached` transforms that cached pose into the local costmap's global frame.
The [nav_2d_utils transform helper](https://github.com/ros-navigation/navigation2/blob/1.3.13/nav2_dwb_controller/nav_2d_utils/src/tf_help.cpp)
first requests the input pose's timestamp; it tries the latest transform only
after an extrapolation exception. In contrast, RotationShim stamps its sampled
goal with the current clock, and
[MPPI goal transformation](https://github.com/ros-navigation/navigation2/blob/1.3.13/nav2_mppi_controller/src/path_handler.cpp)
uses the current robot-pose timestamp supplied by the controller.

With a changing `map` to `odom` transform, those differently timed requests can
produce different odom-frame goal coordinates. That is a source-backed possible
interaction, not a measured sole cause: this artifact lacks the actual historical
and current TF samples needed to demonstrate it during the failed warmup.

The next setup changes only
`local_costmap.local_costmap.ros__parameters.global_frame` from `odom` to `map`
before collecting a new cohort. On this controlled static depot route, a map-frame
local grid removes the map-to-odom goal conversion from the goal-checking/control
comparison. It still depends on live localization and TF for the robot pose.
AMCL corrections can now shift the robot and rolling local grid discontinuously
in that frame; this tradeoff must be measured and is not a general configuration
recommendation or a guarantee of successful arrival.

RotationShim, its MPPI primary and goal-heading flag, every goal/preset setting,
the fixed BT, and other MPPI parameters remain unchanged. The adapter must read
back the actual local-costmap `global_frame` as a typed string before and after
navigation, require `map`, and reject missing or changed frame evidence together
with the existing controller/BT/asset admission checks. The candidate still
changes only `FollowPath.vx_max` from 0.5 to 0.2 m/s; RobotCI's 0.35 m task
tolerance, default 10% duration/path and 0.1 m distance gates, event allowances,
and predeclared baseline-1 rule remain unchanged.

A fresh warmup, five unchanged baselines, all 20 ordered-pair gates, preselected
baseline-1 capture, held-out control, real candidate, and restored control are
required, followed by an
independent fresh repetition of the same frozen setup. Both complete series
remain pending. The failed warmup and all earlier cohorts stay in the evidence
record; no previous run is reused or selected to bypass stability admission.

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
