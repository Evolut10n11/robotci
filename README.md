# RobotCI

Local-first regression testing for ROS2 / Nav2.

RobotCI is an open-source developer tool for running repeatable navigation scenarios in simulation, producing machine-readable results, and eventually comparing candidate robot behavior against a known-good baseline before changes reach a physical robot.

> Status: early alpha. M0–M2 are complete. M3 is in progress and adds runtime navigation telemetry such as path length, distance to goal, stuck events, feedback samples, and recoveries.

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
 later: baseline comparison → REGRESSION
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

Validation rejects malformed YAML, unsupported config versions, duplicate or unsafe scenario names, invalid coordinates, invalid runtimes, and non-positive timeouts before any robotics runtime starts.

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
  "start": {
    "x": 0.0,
    "y": 0.0,
    "yaw": 0.0
  },
  "status": "PASS"
}
```

Current M3 telemetry:

- `path_length_m` — accumulated traveled distance with a small deadband to suppress pose jitter
- `distance_to_goal_m` — latest Nav2 remaining distance, with geometric fallback
- `stuck_events` — number of detected no-motion periods
- `feedback_samples` — number of Nav2 feedback samples processed
- `recoveries` — highest recovery count reported by Nav2

These metrics are collected now so the next regression milestone can compare candidate runs against a baseline instead of gating only on pass/fail.

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

M3 — Metrics 🚧
duration + path length + distance-to-goal + stuck detection + recoveries

M4 — Regression
baseline + candidate comparison + REGRESSION verdict

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
