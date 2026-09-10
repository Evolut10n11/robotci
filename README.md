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
configuration before metrics
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
