# RobotCI

Local-first regression testing for ROS2 / Nav2.

RobotCI is an open-source-first developer tool for running repeatable robot navigation scenarios, collecting machine-readable results, and eventually comparing candidate behavior with a baseline before changes reach a physical robot.

> Status: early alpha. M0 is complete. M1 adds a real multi-scenario runner through one `robotci run` command across native Ubuntu, Docker, and GitHub Actions.

## Why RobotCI

A normal unit test can tell you that a function still returns the expected value. It usually cannot answer the more useful robotics question:

> I changed navigation code or configuration. Can the robot still complete the same tasks as well as before?

RobotCI is being built to make navigation regressions repeatable, measurable, and suitable for CI.

```text
code / config change
        ↓
     git push
        ↓
   RobotCI suite
        ↓
 ROS2 + Nav2 runtime
        ↓
 repeat navigation scenarios
        ↓
 machine-readable results
        ↓
 PASS / FAIL / TIMEOUT / INFRA_ERROR
        ↓
 later: compare with baseline → REGRESSION
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

The core Python package remains cross-platform and is tested on Windows and Ubuntu. ROS imports stay isolated under `robotci.ros` so Windows developers can work on CLI, configuration, result models, reports, and regression logic without installing ROS locally.

## What works today

RobotCI has one user-facing execution command:

```text
robotci run
```

With no `--scenario`, it runs the full built-in suite.

The M1 built-in scenarios are:

| Scenario | Start | Goal |
| --- | --- | --- |
| `short_route` | `(0.0, 0.0, 0.0)` | `(4.0, -0.17, 0.0)` |
| `medium_route` | `(0.0, 0.0, 0.0)` | `(9.0, -0.39, 0.0)` |
| `simple_route` | `(0.0, 0.0, 0.0)` | `(17.86, -0.77, 0.0)` |

Each scenario gets an individual JSON result. The complete run also gets a `suite-result.json` with the aggregate verdict.

```text
robotci run
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
final exit code
```

M1 scenarios intentionally share the same start pose. User-defined starts, goals, maps, and scenario lists move into `robotci.yaml` in M2.

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

RobotCI keeps one repository and one product version while supporting several execution environments.

| Environment | Core CLI | Unit tests | ROS2 / Nav2 | Full suite |
| --- | --- | --- | --- | --- |
| Windows 11 / PowerShell | ✅ | ✅ | optional | via Docker or CI |
| Ubuntu 24.04 native | ✅ | ✅ | ✅ | ✅ |
| Docker Linux container | ✅ | ✅ | ✅ | ✅ |
| GitHub Actions Ubuntu 24.04 | ✅ | ✅ | ✅ | ✅ |

Runtime selection:

```text
auto    native ROS on Linux first, otherwise Docker if available
native  Ubuntu/Linux + local ROS2 Jazzy/Nav2
docker  Docker Compose Linux runtime
```

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

Run the full robotics suite through Docker when a Linux-container backend is available:

```powershell
robotci run --runtime docker
Get-Content .\.robotci\suite-result.json
```

Run only one scenario:

```powershell
robotci run --runtime docker --scenario simple_route
Get-Content .\.robotci\result.json
```

If Docker is unavailable on the Windows machine, core development still works locally and full robotics execution can run in GitHub Actions or on an Ubuntu machine.

## Quick start — Ubuntu 24.04 native

```bash
git clone https://github.com/Evolut10n11/robotci.git
cd robotci
bash scripts/bootstrap_ubuntu.sh

source .venv/bin/activate
robotci doctor
robotci run --runtime native
cat .robotci/suite-result.json
```

Run one scenario when debugging:

```bash
robotci run --runtime native --scenario short_route
cat .robotci/result.json
```

The default timeout is 120 seconds per scenario.

## Quick start — Docker

From a machine with a working Docker engine:

```bash
git clone https://github.com/Evolut10n11/robotci.git
cd robotci

python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

robotci run --runtime docker
cat .robotci/suite-result.json
```

The image itself also runs the suite by default:

```bash
docker compose build
docker compose run --rm robotci
cat artifacts/suite-result.json
```

## Suite result

Example shape:

```json
{
  "duration_sec": 154.321,
  "runtime": "native",
  "scenarios": [
    {
      "duration_sec": 19.2,
      "result_file": ".robotci/results/short_route.json",
      "scenario": "short_route",
      "status": "PASS"
    },
    {
      "duration_sec": 43.4,
      "result_file": ".robotci/results/medium_route.json",
      "scenario": "medium_route",
      "status": "PASS"
    },
    {
      "duration_sec": 88.4,
      "result_file": ".robotci/results/simple_route.json",
      "scenario": "simple_route",
      "status": "PASS"
    }
  ],
  "status": "PASS"
}
```

Individual scenario files still contain start pose, goal pose, duration, navigation result, and verdict.

## GitHub Actions

The repository validates independent layers:

```text
CI
├── Windows / Python 3.12
└── Ubuntu / Python 3.12

ROS smoke
└── ROS2 Jazzy + Nav2 package/API availability

Nav2 Loopback Launch
└── headless runtime + lifecycle readiness

Navigation Suite
└── native Ubuntu + all built-in scenarios + suite-result.json

Docker Runtime
└── image build + all built-in scenarios + suite-result.json
```

This keeps cross-platform core failures separate from robotics runtime failures.

## M0 — Vertical Slice ✅

M0 proved one complete A → B execution:

```text
launch Nav2 Loopback
↓
set initial pose
↓
activate lifecycle nodes
↓
send NavigateToPose
↓
wait for completion
↓
PASS / FAIL / TIMEOUT / INFRA_ERROR
↓
result.json
```

## M1 — Scenario suite ✅

M1 turns the vertical slice into a reusable runner:

```text
robotci run
↓
runtime selection
↓
multiple built-in scenarios
↓
individual results
↓
suite summary
↓
aggregate exit code
```

Single-scenario mode remains available through `--scenario` for debugging and CI isolation.

## Next: M2 — Configuration

The next milestone removes hard-coded scenario definitions from the product workflow.

Target:

```text
robotci.yaml
↓
validation
↓
map / launch / runtime settings
↓
user-defined scenarios
↓
robotci run
```

A future configuration will define starts, goals, timeouts, launch commands, and scenario lists without changing Python source code.

## Planned metrics

After configuration, the first useful regression metrics are:

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
one headless A → B scenario + result.json

Runtime portability ✅
Windows core + Ubuntu native + Docker + GitHub Actions

M1 — Scenario suite ✅
robotci run + multiple scenarios + suite-result.json

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
ROS runtime isolated from core
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
│   ├── runner.py
│   └── scenarios.py
├── scripts/
│   ├── bootstrap_ubuntu.sh
│   ├── run_navigation_scenario.sh
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

Robotics changes should also pass the native Ubuntu suite and Docker suite before merge.

## License

RobotCI is licensed under the Apache License 2.0.
