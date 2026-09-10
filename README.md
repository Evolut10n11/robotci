# RobotCI

Local-first regression testing for ROS2 / Nav2.

RobotCI is an open-source-first developer tool for running repeatable robot navigation scenarios, collecting metrics, comparing results with a baseline, and returning a clear CI verdict before changes reach a physical robot.

> Status: early alpha. The project is currently building the M0 vertical slice.

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
CI verdicts
```

RobotCI is not trying to become a universal robotics platform in the first release.

## Current progress

The Python foundation is working:

```text
Python 3.12
    ↓
RobotCI package
    ↓
CLI
    ↓
pytest
    ↓
Ruff
    ↓
GitHub Actions
```

The ROS integration has also been validated on GitHub-hosted Ubuntu 24.04 runners:

```text
Ubuntu 24.04
    ↓
ROS2 Jazzy
    ↓
Nav2
    ↓
Nav2 Loopback
    ↓
headless bringup
    ↓
map → odom → base_link TF
    ↓
active Nav2 lifecycle nodes
    ↓
/navigate_to_pose available
```

The next product milestone is the first automated A → B navigation scenario.

## Cross-platform development model

RobotCI has one codebase and one version. We do not maintain separate Windows and Linux editions.

| Platform | Core CLI | Unit tests | ROS2 / Nav2 runtime | Full navigation scenarios |
| --- | --- | --- | --- | --- |
| Windows 11 | ✅ | ✅ | not required locally | via Ubuntu / GitHub Actions |
| Ubuntu 24.04 | ✅ | ✅ | ✅ | ✅ |
| GitHub Actions Ubuntu 24.04 | ✅ | ✅ | ✅ | ✅ |

This lets contributors develop the Python core on Windows while robotics-specific integration runs on Ubuntu.

The core package must not import ROS modules during normal startup. ROS is treated as an optional runtime capability rather than a requirement for using the CLI.

## CI architecture

Core checks run on both Windows and Ubuntu:

```text
Pull Request
    ↓
┌─────────────────────┬─────────────────────┐
│ Windows latest      │ Ubuntu 24.04        │
│ Python 3.12         │ Python 3.12         │
│ install RobotCI     │ install RobotCI     │
│ Ruff                │ Ruff                │
│ pytest              │ pytest              │
│ robotci version     │ robotci version     │
└─────────────────────┴─────────────────────┘
```

ROS integration remains Linux-specific:

```text
GitHub Ubuntu 24.04 runner
        ↓
ROS2 Jazzy
        ↓
Nav2
        ↓
Loopback simulator
        ↓
headless readiness checks
```

## Project paths

RobotCI uses `pathlib` and project-relative paths instead of hard-coded Windows or Linux paths.

Runtime artifacts will live under:

```text
.robotci/
└── result.json
```

This avoids platform-specific assumptions such as `/tmp/...` or manually assembled path separators in the Python core.

## Doctor command

Run:

```powershell
robotci doctor
```

On Ubuntu with the supported ROS stack installed, ROS checks are blocking.

On Windows, the core platform is supported and missing ROS is reported as a warning rather than making the core CLI unusable. Full ROS scenarios can be delegated to Ubuntu or GitHub Actions.

## Development setup on Windows

Clone the repository:

```powershell
git clone https://github.com/Evolut10n11/robotci.git
cd robotci
```

Create and activate a Python 3.12 virtual environment:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Install RobotCI in editable mode:

```powershell
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

Verify the CLI:

```powershell
robotci version
```

Expected output:

```text
RobotCI 0.0.1
```

Run the core checks:

```powershell
pytest -vv
ruff check .
robotci doctor
```

## Development setup on Ubuntu 24.04

The Python core is installed the same way:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[dev]"
pytest -vv
ruff check .
```

Ubuntu contributors can additionally install ROS2 Jazzy and Nav2 to run robotics integration locally.

## M0 — Vertical Slice

The first major milestone is intentionally small. RobotCI must execute one complete navigation scenario without manual interaction.

Target flow:

```text
start ROS2 / Nav2
        ↓
start Loopback simulator
        ↓
set initial pose
        ↓
wait for runtime readiness
        ↓
send NavigateToPose goal
        ↓
robot moves A → B
        ↓
wait for result
        ↓
write .robotci/result.json
        ↓
return the correct exit code
```

M0 is complete when the same scenario can be executed repeatedly with a reliable machine-readable verdict.

## Verdict model

RobotCI separates robot behavior failures from infrastructure failures.

| Verdict | Meaning |
| --- | --- |
| `PASS` | The scenario completed and all assertions passed. |
| `FAIL` | Robot behavior failed the scenario or violated an assertion. |
| `REGRESSION` | The candidate is worse than the accepted baseline beyond configured thresholds. |
| `INFRA_ERROR` | ROS, simulator, launch process, environment, or RobotCI infrastructure failed. |

A broken CI environment must not be reported as a navigation regression.

## Planned metrics

The first useful metrics are:

```text
success
duration_sec
path_length_m
stuck_events
process_crash
```

Later simulator-backed stages may add metrics such as collisions, minimum clearance, and recovery count.

## Planned workflow

The intended user experience is eventually:

```text
robotci doctor
robotci run
```

A project-level configuration will describe the runtime, scenario suite, assertions, and regression thresholds. The exact configuration schema is still under design and is not stable yet.

## Roadmap

```text
M0 — Vertical Slice
one headless A → B navigation scenario

M1 — CLI runner
robotci run + multiple scenarios

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

## Non-goals for the MVP

The first version will not include physical robot hardware, Kubernetes, a web dashboard, billing, cloud GPU infrastructure, LLM log analysis, RL training, or support for every simulator and robot.

The project stays small until the core regression workflow proves useful.

## Design principles

```text
local-first
Nav2-first
open-source-first
one Python package before microservices
cross-platform core
ROS runtime isolated from the core
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
│   ├── __init__.py
│   ├── cli.py
│   ├── doctor.py
│   ├── paths.py
│   └── platform.py
├── tests/
│   ├── test_doctor.py
│   ├── test_imports.py
│   ├── test_paths.py
│   └── test_platform.py
├── pyproject.toml
├── README.md
├── LICENSE
└── .gitignore
```

The internal architecture will grow only when the working product requires it.

## Contributing

Prefer small pull requests that produce a runnable or testable result.

Before opening a PR, run:

```powershell
pytest -vv
ruff check .
```

Do not add large abstractions or infrastructure unless they are required by the current milestone.

## License

RobotCI is licensed under the Apache License 2.0.
