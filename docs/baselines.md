# Local baseline workflow

RobotCI can capture a successful suite as a self-contained known-good baseline and compare later candidate runs against it.

The first baseline workflow is intentionally local-first and filesystem-backed. It does not require a hosted service, account, database, or LLM.

## 1. Run and review a known-good suite

```bash
robotci run --runtime native
```

RobotCI writes the suite summary and referenced scenario results under `.robotci/`:

```text
.robotci/
├── suite-result.json
└── results/
    ├── short_route.json
    ├── medium_route.json
    └── simple_route.json
```

Review the result before promoting it. A baseline can only be captured from a `PASS` suite whose referenced scenario results also exist and are `PASS`.
Each referenced result must also contain a valid task fingerprint. Baseline and
candidate fingerprints must match, which prevents a changed start, goal, frame,
or map from being reported as a controller regression result.

## 2. Capture the baseline

```bash
robotci-baseline save main-nav --suite .robotci/suite-result.json
```

The default store is `.robotci/baselines`. The captured baseline is self-contained, so it remains usable after the original run directory is replaced by a later run.

```text
.robotci/baselines/main-nav/
├── manifest.json
├── suite-result.json
└── results/
    ├── short_route.json
    ├── medium_route.json
    └── simple_route.json
```

Use a different store when the baseline should live elsewhere:

```bash
robotci-baseline save main-nav \
  --suite .robotci/suite-result.json \
  --store ./ci-baselines
```

## 3. Inspect captured baselines

```bash
robotci-baseline list
robotci-baseline show main-nav
```

For scripts and tooling, both commands can emit JSON:

```bash
robotci-baseline list --json
robotci-baseline show main-nav --json
```

The metadata includes the baseline name, capture time, original source suite, self-contained suite path, and scenario names.

## 4. Run a candidate and gate regressions

After changing robot code or configuration, run the same suite again:

```bash
robotci run --runtime native
```

Then gate the candidate directly by saved baseline name:

```bash
robotci-baseline gate main-nav \
  --candidate .robotci/suite-result.json \
  --output .robotci/suite-regression.json \
  --markdown-output .robotci/suite-regression.md \
  --junit-output .robotci/suite-regression.xml
```

The gate resolves `.robotci/baselines/main-nav/suite-result.json` automatically. It uses the same deterministic comparison engine and policy as `robotci-suite-gate`.

The default policy allows up to 10% duration and path-length increase and no additional stuck events or recoveries. Override those thresholds explicitly when a repository needs another policy:

```bash
robotci-baseline gate main-nav \
  --candidate .robotci/suite-result.json \
  --max-duration-increase-pct 15 \
  --max-path-length-increase-pct 12 \
  --max-stuck-events-increase 0 \
  --max-recoveries-increase 1
```

For automation, add `--json` to print the machine-readable suite report. The gate exits successfully when the candidate stays within policy and exits with code `4` when it detects a behavioral regression. Invalid baseline or candidate inputs exit with code `3`.

The lower-level path-based command remains available when a suite is not stored in the baseline registry:

```bash
robotci-suite-gate \
  --baseline path/to/baseline/suite-result.json \
  --candidate .robotci/suite-result.json
```

## 5. Intentionally update a baseline

RobotCI never silently overwrites an existing baseline. After reviewing and approving a new known-good run, replacement must be explicit:

```bash
robotci-baseline save main-nav \
  --suite .robotci/suite-result.json \
  --replace
```

## 6. Remove a baseline

```bash
robotci-baseline remove main-nav
```

## Safety rules

Baseline capture rejects:

- failed, timed-out, or infrastructure-error suites;
- non-PASS referenced scenario results;
- missing or corrupt result files;
- duplicate scenario identities inside the suite;
- unsafe result paths that escape the suite directory;
- unsafe baseline names;
- accidental overwrite without `--replace`.

The candidate run is never mutated while a baseline is captured or compared.
