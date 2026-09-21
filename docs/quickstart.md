# RobotCI public alpha quickstart

RobotCI 0.1.0a1 is the first public alpha of the local-first ROS2/Nav2 behavior
regression workflow. The alpha is source-distributed from this repository; it is
not presented as a stable PyPI release yet.

The safe first use is simulation-only:

```text
install
  -> initialize one scenario
  -> validate and inspect the resolved plan
  -> run in simulation
  -> review the PASS evidence
  -> capture a known-good baseline
  -> change code/config
  -> run the same suite
  -> gate the candidate against the baseline
```

## Supported alpha environments

- Python 3.12.
- Ubuntu 24.04 + ROS2 Jazzy/Nav2 for native runtime execution.
- A working Linux-container Docker backend for the Docker runtime.
- Windows 11 for the cross-platform core, configuration, planning, comparison,
  reporting, baselines, and MCP tooling. Full ROS/Nav2 execution should run in
  Docker or GitHub Actions.

The alpha is Nav2-first. It is not a physical-robot safety system, a generic
robotics cloud, or a promise of compatibility with every ROS distribution.

## 1. Install RobotCI

Clone the repository and install the package into a virtual environment.

### Ubuntu / Linux

```bash
git clone https://github.com/Evolut10n11/robotci.git
cd robotci

python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install .

robotci version
```

The expected public-alpha version is:

```text
RobotCI 0.1.0a1
```

### Windows / PowerShell

```powershell
git clone https://github.com/Evolut10n11/robotci.git
cd robotci

py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install .

robotci version
```

## 2. Try the bundled example

Before adapting RobotCI to another repository, validate the bundled Nav2
Loopback example:

```bash
robotci validate --config examples/nav2-loopback/robotci.yaml
robotci plan --config examples/nav2-loopback/robotci.yaml
robotci doctor
```

On Ubuntu with ROS2 Jazzy/Nav2:

```bash
robotci run --config examples/nav2-loopback/robotci.yaml --runtime native
```

With a working Linux-container Docker backend:

```bash
robotci run --config examples/nav2-loopback/robotci.yaml --runtime docker
```

See [../examples/nav2-loopback/README.md](../examples/nav2-loopback/README.md)
for the example contract.

## 3. Initialize RobotCI in a real simulator repository

From the RobotCI environment, initialize the target repository:

```bash
robotci-init --project-root ../my-nav2-project
cd ../my-nav2-project
```

RobotCI creates one validated `robotci.yaml`. It will not overwrite an existing
config unless `--force` is explicitly supplied.

Edit the generated route before running it. At minimum review:

- `map_id`: a stable map name or content digest;
- `start` and `goal`: coordinates that are safe in the simulator;
- `timeout_sec`;
- `goal_tolerance_m`;
- `min_feedback_samples`.

Do not reuse the bundled example coordinates on a physical robot.

## 4. Validate before starting a runtime

```bash
robotci validate
robotci plan
robotci doctor
```

`validate` checks the configuration contract. `plan` resolves the effective
suite without starting ROS or Docker. `doctor` checks whether a native or Docker
runtime is actually available.

Fix configuration or infrastructure errors before running the suite.

## 5. Run and inspect the first simulation suite

```bash
robotci run
```

The default output is:

```text
.robotci/
├── suite-result.json
└── results/
    └── smoke_route.json
```

A successful navigation action is not enough by itself. RobotCI only emits
`PASS` when the configured evidence policy is satisfied, including valid
feedback and final distance to goal.

Review the first suite before promoting it to a baseline.

## 6. Capture a known-good baseline

When the suite is genuinely known-good:

```bash
robotci-baseline save main-nav --suite .robotci/suite-result.json
robotci-baseline show main-nav
```

RobotCI stores a self-contained copy under `.robotci/baselines/main-nav/` and
will not silently replace it.

## 7. Gate a candidate change

After changing planner/controller/configuration code, run the same suite again:

```bash
robotci run
```

Then compare it with the saved baseline:

```bash
robotci-baseline gate main-nav \
  --candidate .robotci/suite-result.json \
  --output .robotci/suite-regression.json \
  --markdown-output .robotci/suite-regression.md \
  --junit-output .robotci/suite-regression.xml
```

A deterministic regression exits with code `4`. Invalid or incompatible
artifacts exit with code `3`. RobotCI does not ask an LLM to decide the verdict.

See [baselines.md](baselines.md) for baseline replacement and policy details.

## 8. Move the gate into GitHub Actions

Once local baseline/candidate comparison is working, use the reusable action in
the pull-request workflow.

See [github-action.md](github-action.md) for the complete workflow, inputs, JSON
report, Markdown summary, JUnit output, and artifact upload example.

For reproducible use, pin the action to a reviewed commit or release tag rather
than following a moving branch.

## 9. Report alpha problems

Before filing a bug, capture the smallest reproducible case and avoid including
credentials, tokens, private paths, or customer data. The support bundle is
designed to expose a redaction-safe diagnostic summary; see
[support-bundle.md](support-bundle.md).

Use the repository issue forms:

- **Bug report** for incorrect RobotCI behavior or broken onboarding.
- **Public alpha pilot feedback** after trying RobotCI on a real ROS2/Nav2
  repository, even if nothing crashed.

The alpha is successful when external teams can independently reach a real suite,
baseline comparison, and repeatable PR gate. Friction reported by those teams is
input to M8 validation.
