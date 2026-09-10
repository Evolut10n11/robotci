# RobotCI

Local-first regression testing for ROS2 / Nav2.

RobotCI is an open-source-first developer tool for running repeatable robot navigation scenarios, collecting machine-readable results, and eventually comparing candidate behavior with a baseline before changes reach a physical robot.

> Status: early alpha. M0 Vertical Slice is complete. The current milestone is M1: turning the proven A → B scenario into a reusable `robotci run` CLI workflow across native Ubuntu, Docker, and CI.

## Why RobotCI

A normal unit test can tell you that a function still returns the expected value. It usually cannot answer a more useful robotics question:

> I changed navigation code or configuration. Can the robot still complete the same task as well as before?

Navigation regressions often only appear at runtime: a planner stops finding a route, a controller becomes slower, a robot gets stuck, success rate drops, or a ROS process dies during execution.

RobotCI aims to make those failures repeatable, measurable, and suitable for CI.

```text
code / config change
        ↓
     git push
        ↓
   RobotCI suite
        ↓
 ROS2 + Nav2 simulation
        ↓
 collect navigation results
        ↓
 compare with baseline
        ↓
 PASS / FAIL / TIMEOUT / REGRESSION / INFRA_ERROR
```

## Current scope

The first supported robotics stack is intentionally narrow:

```text
ROS2 Jazzy
+
Nav2
+
Nav2 Loopback
+
repeatable navigation scenarios
+
machine-readable results
+
CI verdicts
```

RobotCI is not trying to become a universal robotics platform in the first release.

## What works today

The cross-platform Python foundation works on Windows and Ubuntu:

```text
Python 3.12
    ↓
RobotCI package
    ↓
CLI
    ↓
pytest + Ruff
    ↓
Windows / Ubuntu CI
```

The first complete navigation scenario also works end-to-end:

```text
start A = (0.0, 0.0, 0.0)
        ↓
ROS2 Jazzy + Nav2 + Loopback
        ↓
NavigateToPose
        ↓
goal B = (17.86, -0.77, 0.0)
        ↓
PASS / FAIL / TIMEOUT / INFRA_ERROR
        ↓
result.json
```

That path has passed on a clean GitHub-hosted Ubuntu 24.04 runner and inside the Docker runtime.

## Runtime model

RobotCI keeps one repository and one product version while supporting several execution environments.

| Environment | Core CLI | Unit tests | ROS2 / Nav2 | Navigation scenario |
| --- | --- | --- | --- | --- |
| Windows 11 / PowerShell | ✅ | ✅ | optional | via Docker or CI |
| Ubuntu 24.04 native | ✅ | ✅ | ✅ | ✅ |
| Docker Linux container | ✅ | ✅ | ✅ | ✅ |
| GitHub Actions Ubuntu 24.04 | ✅ | ✅ | ✅ | ✅ |

The core package does not import ROS modules during normal startup. ROS remains isolated under `robotci.ros` and is only required when a robotics scenario actually runs.

Docker is not required for core development. Windows users need a working Linux-container backend to use the Docker runtime; otherwise they can still develop the core locally and rely on GitHub Actions or an Ubuntu machine for full robotics execution.

## Unified CLI runner

M1 introduces one user-facing entry point:

```text
robotci run
```

The current alpha supports one scenario, `simple_route`, and three runtime choices:

```text
auto    choose native ROS on Linux, otherwise Docker if available
native  run against local Ubuntu + ROS2 Jazzy/Nav2
docker  build/run the Docker Compose runtime
```

Examples:

```bash
robotci run
robotci run --runtime native
robotci run --runtime docker
robotci run --scenario simple_route --timeout-sec 90
robotci run --output .robotci/result.json
```

The command returns the scenario exit code and writes a machine-readable JSON result.

## Quick start — Windows / PowerShell

Windows is a supported development environment for the RobotCI core.

```powershell
git clone https://github.com/Evolut10n11/robotci.git
cd robotci

py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
pip install -e ".[dev]"

robotci version
robotci doctor
pytest -vv
ruff check .
```

If Docker Desktop or another Linux-container engine is working on the machine, the full scenario can be started from PowerShell with:

```powershell
robotci run --runtime docker
Get-Content .\.robotci\result.json
```

If Docker is installed but its daemon/backend is unavailable, RobotCI reports a runtime error instead of pretending the navigation test failed.

## Quick start — Ubuntu 24.04 native

Clone and bootstrap the supported native robotics environment:

```bash
git clone https://github.com/Evolut10n11/robotci.git
cd robotci
bash scripts/bootstrap_ubuntu.sh
```

Then run:

```bash
source .venv/bin/activate
robotci doctor
robotci run --runtime native
cat .robotci/result.json
```

`robotci run` automatically uses the existing Nav2 Loopback orchestration and returns the final scenario verdict.

## Quick start — Docker

With a working Docker engine:

```bash
git clone https://github.com/Evolut10n11/robotci.git
cd robotci

python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

robotci run --runtime docker
cat .robotci/result.json
```

You can still use the lower-level container commands directly when debugging the runtime:

```bash
docker compose build
docker compose run --rm robotci
```

The image itself starts the scenario through the RobotCI CLI, so Docker and native Ubuntu exercise the same product entry point.

## GitHub Actions

The repository currently validates several layers independently:

```text
CI
├── Windows 11 / Python 3.12
└── Ubuntu 24.04 / Python 3.12

ROS smoke
└── ROS2 Jazzy + Nav2 package/API availability

Nav2 Loopback Launch
└── headless runtime + lifecycle readiness

Navigation Scenario
└── native Ubuntu `robotci run` + result.json

Docker Runtime
└── image build + containerized `robotci run` + result.json
```

This gives the project a clean split: core code stays cross-platform, while the ROS runtime is exercised where Linux robotics dependencies are available.

## Current scenario result

Example result:

```json
{
  "duration_sec": 12.345,
  "goal": {
    "x": 17.86,
    "y": -0.77,
    "yaw": 0.0
  },
  "navigation_result": "SUCCEEDED",
  "scenario": "simple_route",
  "start": {
    "x": 0.0,
    "y": 0.0,
    "yaw": 0.0
  },
  "status": "PASS"
}
```

Exit codes:

```text
0  PASS
1  FAIL
2  TIMEOUT
3  INFRA_ERROR
```

RobotCI deliberately separates robot behavior failures from infrastructure failures. A broken ROS environment or unavailable Docker daemon must not be reported as a navigation regression.

## M0 — Vertical Slice ✅

M0 is complete. RobotCI can launch Nav2 Loopback, set the initial pose, activate the lifecycle nodes, send `NavigateToPose`, wait for A → B completion, and write a machine-readable result.

## M1 — CLI runner 🚧

The current M1 slice adds runtime selection and the `robotci run` command around the proven scenario.

The remaining M1 work is to move from one hard-coded scenario to a real suite model:

```text
robotci run
    ↓
load one or more scenarios
    ↓
select runtime
    ↓
execute scenarios
    ↓
collect individual results
    ↓
produce suite summary
    ↓
return final exit code
```

Configuration files are intentionally deferred to M2. M1 first proves the runner abstraction with the existing working scenario.

## Planned verdict model

| Verdict | Meaning |
| --- | --- |
| `PASS` | The scenario completed and all assertions passed. |
| `FAIL` | Robot behavior failed the scenario or violated an assertion. |
| `TIMEOUT` | Navigation exceeded the scenario timeout. |
| `REGRESSION` | The candidate is worse than the accepted baseline beyond configured thresholds. |
| `INFRA_ERROR` | ROS, simulator, launch process, environment, or RobotCI infrastructure failed. |

`REGRESSION` becomes active once baseline comparison is implemented.

## Planned metrics

The first useful metrics are:

```text
success
duration_sec
path_length_m
stuck_events
process_crash
```

Later simulator-backed stages may add collision count, minimum clearance, and recovery count.

## Roadmap

```text
M0 — Vertical Slice ✅
one headless A → B navigation scenario + result.json

Runtime portability ✅
native Ubuntu + Docker + GitHub Actions

M1 — CLI runner 🚧
robotci run + multiple scenarios + suite summary

M2 — Configuration
robotci.yaml + schema validation

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
```

## Design principles

```text
local-first
Nav2-first
open-source-first
one Python package before microservices
cross-platform core
ROS runtime isolated from the core
native + container runtime parity
reproducibility before feature count
working vertical slices before abstractions
INFRA_ERROR != FAIL
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
│   ├── doctor.py
│   ├── paths.py
│   ├── platform.py
│   ├── results.py
│   └── runner.py
├── scripts/
│   ├── bootstrap_ubuntu.sh
│   └── run_simple_route.sh
├── tests/
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
pytest -vv
ruff check .
```

For robotics changes, also validate the native Ubuntu and/or Docker scenario path before merge.

## License

RobotCI is licensed under the Apache License 2.0.
