# RobotCI

Local-first regression testing for ROS2 / Nav2.

RobotCI is an open-source-first developer tool for running repeatable robot navigation scenarios, collecting machine-readable results, and eventually comparing candidate behavior with a baseline before changes reach a physical robot.

> Status: early alpha. M0 and M1 are complete. M2 adds validated `robotci.yaml` configuration so scenario coordinates and timeouts no longer live in Python source code.

## Why RobotCI

A normal unit test can tell you that a function still returns the expected value. It usually cannot answer the more useful robotics question:

> I changed navigation code or configuration. Can the robot still complete the same tasks as well as before?

RobotCI makes navigation checks repeatable and suitable for CI:

```text
code / config change
        ↓
     git push
        ↓
   RobotCI suite
        ↓
 ROS2 + Nav2 runtime
        ↓
 configured navigation scenarios
        ↓
 machine-readable results
        ↓
 PASS / FAIL / TIMEOUT / INFRA_ERROR
        ↓
 later: baseline comparison → REGRESSION
```

## Current stack

The first supported robotics stack is intentionally narrow:

```text
Python 3.12
+
ROS2 Jazzy
+
Nav2
+
Nav2 Loopback
+
Ubuntu 24.04 / Docker / GitHub Actions
```

The Python core is tested on Windows and Ubuntu. ROS imports stay isolated under `robotci.ros`, so Windows developers can work on CLI, YAML validation, result models, reports, and regression logic without installing ROS locally.

## robotci.yaml

RobotCI reads scenarios from `robotci.yaml` in the project root.

```yaml
version: 1

runtime: auto

scenarios:
  - name: short_route
    start:
      x: 0.0
      y: 0.0
      yaw: 0.0
    goal:
      x: 4.0
      y: -0.17
      yaw: 0.0
    timeout_sec: 60

  - name: medium_route
    start:
      x: 0.0
      y: 0.0
      yaw: 0.0
    goal:
      x: 9.0
      y: -0.39
      yaw: 0.0
    timeout_sec: 90

  - name: simple_route
    start:
      x: 0.0
      y: 0.0
      yaw: 0.0
    goal:
      x: 17.86
      y: -0.77
      yaw: 0.0
    timeout_sec: 120
```

Supported runtime values:

```text
auto    prefer native ROS on Linux, otherwise Docker when available
native  local Linux + ROS2 Jazzy/Nav2
docker  Docker Compose Linux runtime
```

Scenario names must be unique and use only letters, numbers, `_`, or `-`. Start and goal require numeric `x` and `y`; `yaw` defaults to `0.0`. `timeout_sec` must be greater than zero.

## Validate configuration

Validation does not start ROS, so it works on Windows as well as Linux:

```bash
robotci validate
```

Use another config file when needed:

```bash
robotci validate --config path/to/robotci.yaml
```

A valid config prints the runtime and scenario table. Invalid YAML, unsupported versions, duplicate names, unsafe names, invalid coordinates, and non-positive timeouts fail before a robotics runtime starts.

## Run the suite

With no `--scenario`, RobotCI runs every scenario from the YAML file in order:

```bash
robotci run
```

Flow:

```text
robotci.yaml
    ↓
validate
    ↓
select runtime
    ↓
short_route
    ↓
medium_route
    ↓
simple_route
    ↓
individual result JSON files
    ↓
suite-result.json
    ↓
aggregate exit code
```

Run only one configured scenario:

```bash
robotci run --scenario simple_route
```

Override the YAML runtime for one invocation:

```bash
robotci run --runtime native
robotci run --runtime docker
```

Override configured timeouts temporarily:

```bash
robotci run --timeout-sec 120
```

Use another config file:

```bash
robotci run --config path/to/robotci.yaml
```

CLI overrides do not modify the YAML file.

## Verdicts and exit codes

```text
0  PASS
1  FAIL
2  TIMEOUT
3  INFRA_ERROR
```

For a suite, RobotCI returns the worst verdict encountered. For example, if two scenarios pass and one times out, the suite verdict is `TIMEOUT` and the process exits with code `2`.

RobotCI deliberately separates behavior failures from infrastructure failures. A broken ROS environment, unavailable Docker daemon, or missing result file must not be presented as a robot regression.

## Runtime model

RobotCI keeps one repository and one product version across all supported environments.

| Environment | Core CLI | YAML validation | ROS2 / Nav2 | Full suite |
| --- | --- | --- | --- | --- |
| Windows 11 / PowerShell | ✅ | ✅ | optional | via Docker or CI |
| Ubuntu 24.04 native | ✅ | ✅ | ✅ | ✅ |
| Docker Linux container | ✅ | ✅ | ✅ | ✅ |
| GitHub Actions Ubuntu 24.04 | ✅ | ✅ | ✅ | ✅ |

## Quick start — Windows / PowerShell

```powershell
git clone https://github.com/Evolut10n11/robotci.git
cd robotci

py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
pip install -e ".[dev]"

robotci version
robotci validate
pytest -vv
ruff check .
```

If a Linux-container Docker backend is available:

```powershell
robotci run --runtime docker
Get-Content .\.robotci\suite-result.json
```

On a Windows machine without virtualization or Docker, core development and YAML validation still work locally; the full robotics suite can run in GitHub Actions or on Ubuntu.

## Quick start — Ubuntu 24.04 native

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

Each scenario uses its own `timeout_sec` from `robotci.yaml` unless `--timeout-sec` is supplied on the command line.

## Quick start — Docker

From a machine with a working Docker engine:

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

The image also contains the repository `robotci.yaml` and runs that suite by default:

```bash
docker compose build
docker compose run --rm robotci
cat artifacts/suite-result.json
```

## Results

A successful suite produces a summary similar to:

```json
{
  "duration_sec": 154.321,
  "runtime": "native",
  "scenarios": [
    {
      "duration_sec": 19.2,
      "result_file": "results/short_route.json",
      "scenario": "short_route",
      "status": "PASS"
    },
    {
      "duration_sec": 43.4,
      "result_file": "results/medium_route.json",
      "scenario": "medium_route",
      "status": "PASS"
    },
    {
      "duration_sec": 88.4,
      "result_file": "results/simple_route.json",
      "scenario": "simple_route",
      "status": "PASS"
    }
  ],
  "status": "PASS"
}
```

Individual scenario files contain start pose, goal pose, duration, navigation result, and verdict.

## GitHub Actions

The repository validates independent layers:

```text
CI
├── Windows / Python 3.12 / YAML validation
└── Ubuntu / Python 3.12 / YAML validation

ROS smoke
└── ROS2 Jazzy + Nav2 package/API availability

Nav2 Loopback Launch
└── headless runtime + lifecycle readiness

Navigation Suite
└── native Ubuntu + robotci.yaml + suite-result.json

Docker Runtime
└── image build + robotci.yaml + suite-result.json
```

The native and Docker workflows also verify that the goals written to scenario results match the YAML configuration.

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

M2 — Configuration 🚧
robotci.yaml + validation + config-driven start/goal/timeout/runtime

M3 — Metrics
duration + path length + stuck detection

M4 — Regression
baseline + candidate comparison

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

```text
robotci validate
pytest -vv
ruff check .
```

Robotics changes should also pass the native Ubuntu YAML suite and Docker YAML suite before merge.

## License

RobotCI is licensed under the Apache License 2.0.
