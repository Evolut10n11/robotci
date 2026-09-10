# RobotCI

Local-first regression testing for ROS2 / Nav2.

RobotCI is an open-source-first developer tool for running repeatable robot navigation scenarios, collecting metrics, comparing results with a baseline, and returning a clear CI verdict before changes reach a physical robot.

> Status: early alpha. M0 Vertical Slice is complete. The current focus is making the same runtime reproducible from native Ubuntu, Docker, and CI before building the general `robotci run` suite runner.

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
 collect navigation metrics
        ↓
 compare with baseline
        ↓
 PASS / FAIL / REGRESSION / INFRA_ERROR
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

The cross-platform Python foundation is working on Windows and Ubuntu:

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

The first complete navigation scenario is also working:

```text
clean Ubuntu 24.04 runner
        ↓
ROS2 Jazzy
        ↓
Nav2 + Loopback
        ↓
start pose A = (0.0, 0.0, 0.0)
        ↓
NavigateToPose
        ↓
goal B = (17.86, -0.77, 0.0)
        ↓
PASS / FAIL / TIMEOUT / INFRA_ERROR
        ↓
artifacts/simple-route/result.json
```

The scenario has already passed end-to-end in GitHub Actions. This is the first RobotCI test that validates robot behavior rather than only checking that ROS packages and nodes exist.

## Runtime model

RobotCI keeps one repository and one product version while supporting different development/runtime environments.

| Environment | Core CLI | Unit tests | ROS2 / Nav2 | A → B scenario |
| --- | --- | --- | --- | --- |
| Windows 11 / PowerShell | ✅ | ✅ | optional | via Docker, Ubuntu, or CI |
| Ubuntu 24.04 native | ✅ | ✅ | ✅ | ✅ |
| Docker Linux container | ✅ | ✅ | ✅ | ✅ |
| GitHub Actions Ubuntu 24.04 | ✅ | ✅ | ✅ | ✅ |

The core package must not import ROS modules during normal startup. ROS is an optional runtime capability isolated under `robotci.ros`.

Docker is not required for core development. On Windows, running Linux Docker containers requires a working virtualization-backed Docker engine. If that is unavailable, contributors can still develop the core locally and use GitHub Actions or an Ubuntu machine for full navigation runs.

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

Expected version output:

```text
RobotCI 0.0.1
```

Missing ROS on Windows is reported as a warning rather than making the core CLI unusable.

## Quick start — Ubuntu 24.04 native

For a clean Ubuntu 24.04 machine, bootstrap ROS2 Jazzy, Nav2, the Python environment, and RobotCI with:

```bash
git clone https://github.com/Evolut10n11/robotci.git
cd robotci

bash scripts/bootstrap_ubuntu.sh
```

Then run the current end-to-end scenario:

```bash
bash scripts/run_simple_route.sh
```

The result is written to:

```text
artifacts/simple-route/result.json
```

Inspect it with:

```bash
cat artifacts/simple-route/result.json
```

The Ubuntu bootstrap intentionally targets Ubuntu 24.04 + ROS2 Jazzy, which is the supported native robotics environment for the current alpha.

## Quick start — Docker

RobotCI also provides a reproducible Linux-container runtime based on ROS2 Jazzy.

Build and run with Docker Compose:

```bash
docker compose build
docker compose run --rm robotci
```

Or directly with Docker:

```bash
docker build -t robotci:dev .
docker run --rm \
  -v "$(pwd)/artifacts:/workspace/artifacts" \
  robotci:dev
```

The container runs the same `simple_route` scenario and writes the same result format to:

```text
artifacts/simple-route/result.json
```

On a Windows machine where Docker Desktop and Linux containers are available, the Compose commands are the same from PowerShell:

```powershell
docker compose build
docker compose run --rm robotci
Get-Content .\artifacts\simple-route\result.json
```

## Quick start — GitHub Actions

A contributor who has no local ROS2 installation can still run the complete robotics path through GitHub Actions.

Current workflows validate:

```text
CI
├── Windows 11 / Python 3.12
└── Ubuntu 24.04 / Python 3.12

ROS smoke
└── ROS2 Jazzy + Nav2 package/API availability

Nav2 Loopback Launch
└── headless runtime + lifecycle readiness

Navigation Scenario
└── native Ubuntu A → B + result.json

Docker Runtime
└── image build + containerized A → B + result.json
```

## Current scenario result

The current machine-readable result contains the scenario name, verdict, duration, start/goal poses, and the Nav2 action result.

Example shape:

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

Current scenario exit codes:

```text
0  PASS
1  FAIL
2  TIMEOUT
3  INFRA_ERROR
```

RobotCI deliberately separates robot behavior failures from infrastructure failures. A broken ROS environment must not be reported as a navigation regression.

## Doctor command

Run:

```text
robotci doctor
```

On Ubuntu with the supported ROS stack installed, ROS checks are blocking.

On Windows, missing ROS is non-blocking because Windows remains a supported environment for core/CLI development.

## M0 — Vertical Slice ✅

M0 is complete.

The project can now execute one navigation scenario without manual interaction:

```text
launch ROS2 / Nav2
        ↓
start Loopback simulator
        ↓
set initial pose
        ↓
activate Nav2 lifecycle
        ↓
send NavigateToPose goal
        ↓
robot moves A → B
        ↓
wait for result
        ↓
write result.json
        ↓
return machine-readable verdict + exit code
```

This path has passed on a clean GitHub-hosted Ubuntu 24.04 runner.

## Next milestone — M1 runner

The next product step is to stop treating `simple_route` as a special integration script and turn it into a reusable RobotCI runner.

Target user experience:

```text
robotci run
```

Then:

```text
load scenario suite
        ↓
select runtime
        ↓
run one or more scenarios
        ↓
collect results
        ↓
produce suite summary
        ↓
return final exit code
```

The intended runtime choices are native Ubuntu and Docker, while GitHub Actions acts as the remote CI execution environment. Windows continues to support the core CLI and can invoke Docker when the host has a working Docker engine.

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

Runtime portability — in progress
same scenario from native Ubuntu + Docker + GitHub Actions

M1 — CLI runner
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
│       ├── ci.yml
│       ├── docker.yml
│       ├── navigation-scenario.yml
│       ├── nav2-loopback.yml
│       └── ros-smoke.yml
├── robotci/
│   ├── ros/
│   │   ├── __init__.py
│   │   └── navigation_scenario.py
│   ├── __init__.py
│   ├── cli.py
│   ├── doctor.py
│   ├── paths.py
│   ├── platform.py
│   └── results.py
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

The internal architecture grows only when a working product slice requires it.

## Contributing

Prefer small pull requests that produce a runnable or testable result.

Core checks:

```text
pytest -vv
ruff check .
```

For robotics changes, also validate the native Ubuntu and/or Docker scenario path before merge.

## License

RobotCI is licensed under the Apache License 2.0.
