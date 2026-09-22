# Configuration and result contracts

RobotCI uses `robotci.yaml` as the source of truth for scenarios:

```yaml
version: 1
runtime: auto

scenarios:
  - name: short_route
    map_id: nav2-loopback
    start:
      x: 0.0
      y: 0.0
      yaw: 0.0
    goal:
      x: 4.0
      y: -0.17
      yaw: 0.0
    timeout_sec: 60
    goal_tolerance_m: 0.25
    min_feedback_samples: 1

  - name: medium_route
    map_id: nav2-loopback
    start:
      x: 0.0
      y: 0.0
      yaw: 0.0
    goal:
      x: 9.0
      y: -0.39
      yaw: 0.0
    timeout_sec: 90
    goal_tolerance_m: 0.25
    min_feedback_samples: 1

  - name: simple_route
    map_id: nav2-loopback
    start:
      x: 0.0
      y: 0.0
      yaw: 0.0
    goal:
      x: 17.86
      y: -0.77
      yaw: 0.0
    timeout_sec: 120
    goal_tolerance_m: 0.25
    min_feedback_samples: 1
```

Runtime values:

```text
auto    prefer native ROS on Linux, otherwise Docker when available
native  local Linux + ROS2 Jazzy/Nav2
docker  Docker Compose Linux runtime
```

Validate configuration without starting ROS:

```bash
robotci validate
robotci validate --config examples/nav2-loopback/robotci.yaml
```

`validate`, `plan`, and `run` resolve the same project context. With the default
configuration name, RobotCI searches the current directory and its parents for
`robotci.yaml`. An explicit config path anchors the default `.robotci` outputs to
that config's directory, while RobotCI's own runtime scripts remain installation
resources.

Validation rejects malformed YAML, duplicate or unknown keys, unsupported config
versions, duplicate or unsafe scenario names, invalid or non-finite coordinates,
invalid runtimes, and non-positive or non-finite timeouts before any robotics
runtime starts.

Each scenario also defines its deterministic PASS evidence policy.
`goal_tolerance_m` is the maximum measured final distance to the goal, and
`min_feedback_samples` is the minimum number of Nav2 feedback messages. Their
defaults are `0.25` meters and `1`; set them explicitly when the test environment
needs a calibrated tolerance.

Set `map_id` to a stable map name or, preferably, a content digest. RobotCI includes
the scenario name, start, goal, coordinate frame, and `map_id` in the task
fingerprint. Controller and planner implementations are intentionally excluded so
their behavior can be compared on the same task. Results without a real map
identity cannot be used as regression baselines.

## Running scenarios

Run every configured scenario in order:

```bash
robotci run
```

Run one scenario:

```bash
robotci run --scenario simple_route
```

Temporary CLI overrides:

```bash
robotci run --runtime native
robotci run --runtime docker
robotci run --timeout-sec 120
robotci run --config examples/nav2-loopback/robotci.yaml
```

CLI overrides do not modify `robotci.yaml`.

## Results and metrics

A suite writes one summary plus one JSON file per scenario:

| Artifact | Location |
| --- | --- |
| Suite summary | `.robotci/suite-result.json` |
| Scenario result | `.robotci/results/short_route.json` |
| Recorded replay | `.robotci/results/short_route.replay.json` |

Individual scenario results include the configured start and goal, verdict, duration, Nav2 result, and runtime navigation telemetry:

```json
{
  "duration_sec": 19.2,
  "evidence_policy": {
    "goal_tolerance_m": 0.25,
    "min_feedback_samples": 1
  },
  "goal": {
    "x": 4.0,
    "y": -0.17,
    "yaw": 0.0
  },
  "metrics": {
    "distance_to_goal_m": 0.08,
    "feedback_samples": 181,
    "path_length_m": 4.12,
    "recoveries": 0,
    "stuck_events": 0
  },
  "navigation_result": "SUCCEEDED",
  "scenario": "short_route",
  "schema_version": 2,
  "start": {
    "x": 0.0,
    "y": 0.0,
    "yaw": 0.0
  },
  "status": "PASS",
  "telemetry_quality": {
    "final_pose_valid": true,
    "invalid_pose_samples": 0,
    "received_feedback_samples": 181,
    "valid_pose_samples": 181
  },
  "task": {
    "fingerprint": "sha256:116dc24253afb5f8ddfb89d119a48f814e01fdf7aaf14f6f737f40fa8a3757f1",
    "frame_id": "map",
    "map_id": "nav2-loopback",
    "schema_version": 1
  }
}
```

RobotCI uses one result reader for runtime finalization, baseline capture, and
comparison. Result schema v2 is validated strictly, including finite numeric
values, task identity, metrics, telemetry quality, the evidence policy, status,
and navigation outcome. Legacy v0 files and schema v1 files without evidence
quality remain readable for inspection, but they cannot become a baseline or
enter a regression comparison. Unknown future schema versions fail with an
explicit compatibility error.
When a runtime result is missing or malformed, RobotCI writes a current
`INFRA_ERROR` result with `metrics: null` and a machine-readable `reason_code`
instead of inventing zero-valued measurements.

### Suite evidence consistency

Loading a suite validates every referenced scenario file, including its result
schema. Each summary entry must match that file's scenario name and status.
Its `duration_sec` must match within an absolute tolerance of `0.002` seconds;
no relative tolerance is applied, even for long runs.

The suite status must equal the highest-severity scenario status, ordered
`PASS < FAIL < TIMEOUT < INFRA_ERROR`. The suite's own `duration_sec` measures
total execution wall-clock time, including setup and overhead. It is independent
of the individual navigation durations and is not required to equal their sum.

Baseline capture, suite comparison, the viewer, and the application/MCP layer
reuse the scenario snapshots validated by this shared reader. Consistent failed
suites and supported legacy scenario results remain available for inspection;
baseline capture and regression comparison still require current,
evidence-complete `PASS` results.

The reader reports `invalid_result` when a referenced result cannot be read or
fails schema validation, and `inconsistent_result` when its scenario, status, or
duration disagrees with the summary. An incorrect aggregate suite status is
`invalid_metadata`. Missing files retain `missing_result_file`.
These checks do not change the JSON format version.

Keep the summary and scenario files from the same completed run together.
Consistency checks do not establish cryptographic run identity or make
concurrent writes safe. Parallel suites sharing an output directory remain
unsupported.

### Navigation telemetry

- `duration_sec` — monotonic wall-clock time from goal dispatch to the terminal navigation result; pre-dispatch infrastructure errors record elapsed setup time for diagnostics
- `path_length_m` — accumulated distance between valid feedback poses, with a small deadband to suppress pose jitter
- `distance_to_goal_m` — straight-line distance from the latest valid feedback pose to the configured goal
- `stuck_events` — number of no-motion periods detected after goal dispatch
- `feedback_samples` — number of distinct Nav2 feedback messages received
- `recoveries` — highest cumulative recovery count reported by Nav2, including feedback whose pose is invalid

`telemetry_quality` records valid and invalid pose samples and whether the final
feedback pose was valid. A Nav2 `SUCCEEDED` outcome becomes `PASS` only when the
configured minimum feedback is present, no pose sample is invalid, the final pose
is valid, and `distance_to_goal_m` is at or below `goal_tolerance_m`. Missing or
invalid evidence is `INFRA_ERROR`; a measured goal-tolerance violation is `FAIL`.

## Regression contract

RobotCI compares only current, evidence-complete `PASS` results for the same scenario,
start, goal, coordinate frame, map, and evidence policy. A mismatch is an input
error rather than a behavioral verdict. The default deterministic policy flags:

- duration increases above 10%;
- path-length increases above 10%;
- final distance-to-goal increases above 0.1 m;
- any additional stuck event;
- any additional recovery.

Distance uses an absolute meter delta because percentage changes become unstable
near a zero-distance baseline. Threshold equality is inclusive, while any excess
produces `REGRESSION` and exit code `4`. Suite paths are confined to their own
artifact directory before referenced scenario results are loaded.

## Reproducibility contract

RobotCI versions every suite result and fingerprints both the effective execution
plan and the actual runtime environment. The plan covers scenario order, poses,
map, effective timeouts, and evidence policies. Environment provenance covers
host/container isolation, Ubuntu, architecture, Python, ROS Jazzy, RobotCI
dependencies, the installed Nav2 packages, and a digest of the executable
RobotCI Python and runtime shell sources.

Baseline capture and suite comparison validate those fingerprints and require an
exact execution match before reading metrics. Dependency drift or a native-vs-
Docker mismatch is an input error, never a robot verdict. Pre-M5 suites must be
rerun. See [reproducibility.md](reproducibility.md) for the contract
and upgrade behavior.

## Verdicts and exit codes

| Code | Meaning |
| ---: | --- |
| 0 | PASS |
| 1 | FAIL |
| 2 | TIMEOUT |
| 3 | INFRA_ERROR or invalid comparison input |
| 4 | REGRESSION (comparison commands) |

For a suite, RobotCI returns the worst verdict encountered. Infrastructure problems remain separate from robot behavior failures by design:

`INFRA_ERROR` and behavior `FAIL` remain distinct.

A broken ROS environment, unavailable Docker daemon, or missing result file must not be reported as a robot regression.
