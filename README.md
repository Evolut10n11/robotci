# RobotCI

Local-first regression testing for ROS2 / Nav2.

RobotCI is an open-source developer tool for running repeatable navigation scenarios in simulation, producing machine-readable results, and eventually comparing candidate robot behavior against a known-good baseline before changes reach a physical robot.

> Status: early alpha. M0–M4 are complete. RobotCI now captures evidence-qualified navigation telemetry and deterministically gates candidate behavior against known-good baselines.

## Why RobotCI

A normal unit test can tell you whether a function still returns the expected value. It usually cannot answer the robotics question that matters after a navigation change:

> Can the robot still complete the same tasks as well as before?

RobotCI turns that question into a repeatable CI workflow:

```text
code / config change
        ↓
     RobotCI
        ↓
 robotci.yaml
        ↓
 ROS2 + Nav2 runtime
        ↓
 navigation scenarios
        ↓
 result JSON + telemetry
        ↓
 PASS / FAIL / TIMEOUT / INFRA_ERROR
        ↓
 baseline comparison → PASS / REGRESSION
```

## Current stack

```text
Python 3.12
ROS2 Jazzy
Nav2
Nav2 Loopback
Ubuntu 24.04
Docker
GitHub Actions
```

The Python core is tested on both Windows and Ubuntu. ROS imports stay isolated under `robotci.ros`, so Windows contributors can work on the CLI, YAML validation, result models, metrics logic, reporting, and regression logic without installing ROS locally.

## Quick start

### Windows / PowerShell

```powershell
git clone https://github.com/Evolut10n11/robotci.git
cd robotci

py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"

robotci version
robotci validate
robotci doctor
pytest -vv
ruff check .
```

Windows without virtualization can develop and test the cross-platform core locally. Run the full ROS2 / Nav2 suite in GitHub Actions or on Ubuntu.

If a Linux-container Docker backend is available:

```powershell
robotci run --runtime docker
Get-Content .\.robotci\suite-result.json
```

### Ubuntu 24.04 native

```bash
git clone https://github.com/Evolut10n11/robotci.git
cd robotci
bash scripts/bootstrap_ubuntu.sh

source .venv/bin/activate
robotci validate
robotci doctor
robotci run --runtime native
cat .robotci/suite-result.json
```

### Docker

```bash
git clone https://github.com/Evolut10n11/robotci.git
cd robotci

python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

robotci validate
robotci run --runtime docker
cat .robotci/suite-result.json
```

The container can also be started directly:

```bash
docker compose build
docker compose run --rm robotci
cat artifacts/suite-result.json
```

## Configuration

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
robotci validate --config path/to/robotci.yaml
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
robotci run --config path/to/robotci.yaml
```

CLI overrides do not modify `robotci.yaml`.

## Results and metrics

A suite writes one summary plus one JSON file per scenario:

```text
.robotci/
├── suite-result.json
└── results/
    ├── short_route.json
    ├── medium_route.json
    └── simple_route.json
```

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

M3 telemetry contract:

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

M4 compares only current, evidence-complete `PASS` results for the same scenario,
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

## Verdicts and exit codes

```text
0  PASS
1  FAIL
2  TIMEOUT
3  INFRA_ERROR
```

For a suite, RobotCI returns the worst verdict encountered. Infrastructure problems remain separate from robot behavior failures by design:

```text
INFRA_ERROR != FAIL
```

A broken ROS environment, unavailable Docker daemon, or missing result file must not be reported as a robot regression.

## Runtime support

| Environment | Core CLI | YAML validation | ROS2 / Nav2 | Full suite |
| --- | --- | --- | --- | --- |
| Windows 11 / PowerShell | ✅ | ✅ | optional | via Docker or CI |
| Ubuntu 24.04 native | ✅ | ✅ | ✅ | ✅ |
| Docker Linux container | ✅ | ✅ | ✅ | ✅ |
| GitHub Actions Ubuntu 24.04 | ✅ | ✅ | ✅ | ✅ |

RobotCI keeps one repository and one product version across all supported environments.

## GitHub Actions

The repository checks independent layers:

```text
CI
├── Windows / Python 3.12 / YAML validation / unit tests / Ruff
└── Ubuntu / Python 3.12 / YAML validation / unit tests / Ruff

ROS smoke
└── ROS2 Jazzy + Nav2 package/API availability

Nav2 Loopback Launch
└── headless runtime + TF + lifecycle readiness

Navigation Suite
└── native Ubuntu + robotci.yaml + scenario telemetry

Docker Runtime
└── image build + robotci.yaml + scenario telemetry
```

The native and Docker workflows verify both configured goals and runtime metrics written into scenario result files.

## Product vision

RobotCI should evolve from a Nav2-specific regression CLI into a general robot-behavior CI platform. The core idea remains deterministic: run the same robot task before and after a change, measure behavior, compare against a baseline, and block regressions before they reach physical hardware.

```text
code / config / controller / policy change
                    ↓
                 RobotCI
                    ↓
          robot + simulator adapter
                    ↓
             repeatable scenario
                    ↓
       metrics + logs + replay/video
                    ↓
          baseline vs candidate
                    ↓
 PASS / FAIL / TIMEOUT / INFRA_ERROR / REGRESSION
                    ↓
             CI / pull-request gate
```

The current ROS2/Nav2 vertical slice is the proving ground, not the final product boundary.

### Robot and simulator adapters

RobotCI should eventually support multiple robot and simulator backends behind a stable scenario/result interface. Candidate backends include:

```text
Nav2 + Loopback
Gazebo
MuJoCo
Isaac Sim / Isaac Lab
Unitree simulation stacks
custom ROS2 robots
```

The first non-Nav2 target should be a publicly reproducible quadruped setup, with Unitree Go2 + MuJoCo as a strong candidate. Later targets may include Unitree G1/H1-class humanoids, other quadrupeds, robot arms, and additional mobile robots.

A future configuration may look conceptually like this:

```yaml
robot:
  type: unitree_go2

simulator:
  type: mujoco

controller:
  type: sport_mode

scenario:
  name: rough_terrain
  goal:
    x: 10.0
    y: 0.0

checks:
  max_duration_sec: 20
  max_falls: 0
  max_roll_deg: 25
```

Robot-specific behavior belongs in adapters; regression semantics, result storage, reporting, and CI integration should remain shared.

### Behavior metrics beyond navigation

For Nav2, useful metrics include duration, path length, distance to goal, stuck events, recoveries, and path deviation.

For quadrupeds and humanoids, RobotCI should be able to extend the same result model with metrics such as:

```text
falls
body roll / pitch
foot slip
velocity tracking error
energy consumption
joint-limit violations
collisions
terrain completion
stability
```

A scenario can technically PASS while still being a regression. For example, a robot may reach the goal but take 40% longer, use substantially more energy, or introduce repeated stuck events. Baseline comparison must catch these cases deterministically.

### Visual replay and live simulation

RobotCI should not be a logs-only product. A user should be able to see the robot move through the scenario.

The target experience is:

```text
scenario run
    ↓
simulator rendering
    ↓
recording / replay artifact
    ↓
RobotCI report or web UI
```

A run should eventually expose:

- the robot moving in the simulated scene;
- start, goal, obstacles, and trajectory;
- important events such as stuck, recovery, collision, or fall;
- synchronized metrics and timestamps;
- downloadable or browser-viewable replay/video artifacts.

For regression debugging, a side-by-side baseline/candidate view is a major product goal:

```text
BASELINE                      CANDIDATE
robot v1                      robot v2
12.4 s                        15.8 s
0 stuck                       2 stuck
path 11.9 m                   path 14.8 m

       synchronized replay / trajectory comparison
```

A future UI should allow a developer to click a regression and jump directly to the relevant timestamp in the replay.

### AI-native workflow: MCP + LangGraph

LLMs should sit above the deterministic RobotCI engine, not replace it.

RobotCI should expose an MCP server so an agent can safely inspect and operate the test system through explicit tools. A future tool surface may include:

```text
list_scenarios()
plan_run()
run_scenario()
run_suite()
get_result()
compare_runs()
get_metrics()
get_logs()
get_replay()
get_failure_window()
```

An LLM agent implemented with LangGraph/LangChain can then orchestrate stateful workflows such as:

```text
UNDERSTAND
    ↓
PLAN
    ↓
RUN
    ↓
COLLECT
    ↓
COMPARE
    ↓
DIAGNOSE
    ↓
REPORT
```

If a run fails, the graph may branch into log inspection, targeted retry, another scenario, or deeper diagnosis instead of ending immediately.

Combined with GitHub tools/MCP, the intended interaction becomes:

```text
"Check the latest PR and explain any robot regression."
                    ↓
              LLM / LangGraph
              ↙             ↘
         GitHub tools     RobotCI MCP
              ↓               ↓
            diff        simulator/tests
              ↘               ↙
           metrics + logs + replay
                    ↓
             diagnosis/report
```

The agent may explain results, correlate a source-code diff with changed behavior, summarize CI failures, suggest the most likely root cause, and point to the relevant replay timestamp.

For visual failures, a multimodal model may inspect selected replay frames or a short failure window. It should not need to watch an entire run when deterministic telemetry already identifies the suspicious time range.

### Deterministic core, probabilistic explanation

The LLM must not be the source of truth for regression verdicts.

Bad design:

```text
metrics → LLM → "this looks like a regression"
```

Target design:

```text
baseline + candidate
        ↓
RobotCI deterministic policy
        ↓
REGRESSION + exact metric deltas
        ↓
LLM explanation / diagnosis / suggested next step
```

Safety-critical release gates, thresholds, exit codes, metric calculations, and pass/fail/regression decisions should remain deterministic and testable. LLM output is an explanation and engineering assistant layer.

### Model routing and local inference

The AI layer should be model-agnostic. Cheap or local models can handle repository exploration, log summarization, simple CI diagnosis, report generation, and routine tool orchestration. Stronger cloud models can be reserved for difficult debugging, architecture, multimodal replay analysis, or repeated failures.

Persistent state should live in RobotCI results, Git history, CI artifacts, MCP-visible state, and explicit agent state rather than inside one model conversation. This allows local and cloud models to hand work off without losing project context.

### Commercial direction

The open-source core should remain useful by itself: local scenarios, deterministic metrics, baseline comparison, regression verdicts, replay artifacts, MCP tools, and CI integration.

A possible paid layer should focus on team coordination and persistent history rather than hiding the local runner:

```text
persistent baseline registry
historical run trends
GitHub PR regression reports
team policy gates
flaky-run detection
private artifact / replay retention
hosted history
self-hosted enterprise control plane
SSO / audit / retention / support
AI-assisted regression diagnosis
```

The first paid signal should be whether robotics teams value persistent history, PR gating, replay comparison, and team workflows enough to pay for them. A generic cloud platform should not be built before the deterministic local product proves useful.

## Milestones

```text
M0 — Vertical Slice ✅
one headless A → B scenario + result.json

Runtime portability ✅
Windows core + Ubuntu native + Docker + GitHub Actions

M1 — Scenario suite ✅
robotci run + multiple scenarios + suite-result.json

M2 — Configuration ✅
robotci.yaml + validation + config-driven start/goal/timeout/runtime

M3 — Metrics ✅
duration + path length + distance-to-goal + stuck detection + recoveries

M4 — Regression ✅
baseline + candidate comparison + deterministic REGRESSION verdict

M5 — Reproducibility
repeatable clean-environment execution

M6 — CI integration
JUnit + artifacts + PR release gate

M7 — Public Alpha
quickstart + examples + external users

M8 — Validation
real-world feedback and product direction decision

M9 — Visual replay
recorded simulator runs + trajectory/event timeline + baseline/candidate replay

M10 — Robot adapters
adapter interface + first non-Nav2 robot backend; target: Unitree Go2 + MuJoCo

M11 — MCP / agent API
RobotCI MCP server + LangGraph reference agent + GitHub-aware diagnosis

M12 — Team product validation
persistent baselines + history + PR reports + first paid-signal experiments
```

## Design principles

```text
local-first
Nav2-first, not Nav2-only
open-source-first
one Python package before microservices
cross-platform core
ROS runtime isolated from core
native + container runtime parity
configuration before metrics
reproducibility before feature count
working vertical slices before abstractions
INFRA_ERROR != FAIL
deterministic verdicts before LLM explanations
replayable behavior before opaque AI diagnosis
robot/simulator adapters before backend-specific forks
```

## Repository structure

```text
robotci/
├── .github/
│   └── workflows/
├── robotci/
│   ├── ros/
│   │   ├── __init__.py
│   │   └── navigation_scenario.py
│   ├── __init__.py
│   ├── cli.py
│   ├── config.py
│   ├── doctor.py
│   ├── evidence.py
│   ├── metrics.py
│   ├── paths.py
│   ├── platform.py
│   ├── results.py
│   └── runner.py
├── scripts/
│   ├── bootstrap_ubuntu.sh
│   ├── run_navigation_scenario.sh
│   └── run_simple_route.sh
├── tests/
├── robotci.yaml
├── Dockerfile
├── compose.yaml
├── pyproject.toml
├── README.md
├── LICENSE
└── .gitignore
```

## Contributing

Core checks:

```bash
robotci validate
pytest -vv
ruff check .
```

Robotics changes should also pass the native Ubuntu navigation suite and Docker runtime workflow before merge.

## License

Apache License 2.0.
