# RobotCI GitHub suite regression gate

RobotCI can be used directly as a composite GitHub Action. The action compares a complete candidate `suite-result.json` with a known-good suite and fails the job when any scenario exceeds the configured deterministic regression policy.

The action writes three complementary artifacts:

- versioned JSON for machines and downstream automation;
- Markdown for reviewers and `GITHUB_STEP_SUMMARY`;
- JUnit XML for standard CI test-reporting surfaces.

## Example

```yaml
name: Robot behavior regression

on:
  pull_request:

jobs:
  regression:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v4

      # Produce or download both suite artifacts before this step.
      # Each suite-result.json keeps its scenario result files under paths
      # relative to the suite file (normally results/<scenario>.json).
      - name: Block robot behavior regressions
        id: robotci
        uses: Evolut10n11/robotci@main
        with:
          baseline: artifacts/baseline/suite-result.json
          candidate: artifacts/candidate/suite-result.json
          report: artifacts/suite-regression-report.json
          summary: artifacts/suite-regression-summary.md
          junit: artifacts/suite-regression-junit.xml
          max-duration-increase-pct: "10"
          max-path-length-increase-pct: "10"
          max-distance-to-goal-increase-m: "0.1"
          max-stuck-events-increase: "0"
          max-recoveries-increase: "0"

      - name: Upload regression artifacts
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: robotci-suite-regression-report
          path: |
            artifacts/suite-regression-report.json
            artifacts/suite-regression-summary.md
            artifacts/suite-regression-junit.xml
```

The action installs RobotCI from the referenced action revision and runs `robotci-suite-gate`. Baseline and candidate suites must both be successful, contain the same scenario names, and keep the individual scenario result files referenced by their suite artifact. The gate aggregates the deterministic per-scenario comparisons into one `PASS` or `REGRESSION` verdict.

A regression returns RobotCI exit code `4`, which fails the action step. Invalid or incomplete comparison artifacts return exit code `3`. JSON, Markdown, and JUnit outputs are written before the regression exit, so all remain available when a pull request is blocked. The Markdown file is also appended to `GITHUB_STEP_SUMMARY` automatically.

The JUnit report emits one testcase per RobotCI scenario. Deterministic `REGRESSION` verdicts become JUnit failures with the metric findings in the failure body; passing scenarios remain normal successful testcases. This lets CI systems display RobotCI behavior regressions alongside ordinary automated test results without parsing RobotCI-specific JSON.

For reproducible production use, pin the action to a release tag or commit SHA rather than `main`.

## Inputs

| Input | Default | Meaning |
| --- | --- | --- |
| `baseline` | required | Known-good `suite-result.json` |
| `candidate` | required | Candidate `suite-result.json` |
| `report` | `artifacts/suite-regression-report.json` | Generated JSON suite report path |
| `summary` | `artifacts/suite-regression-summary.md` | Generated Markdown summary path |
| `junit` | `artifacts/suite-regression-junit.xml` | Generated JUnit XML report path |
| `max-duration-increase-pct` | `10` | Allowed duration increase per scenario (%) |
| `max-path-length-increase-pct` | `10` | Allowed path-length increase per scenario (%) |
| `max-distance-to-goal-increase-m` | `0.1` | Allowed final distance-to-goal increase per scenario (m) |
| `max-stuck-events-increase` | `0` | Allowed additional stuck events per scenario |
| `max-recoveries-increase` | `0` | Allowed additional recoveries per scenario |

## Outputs

- `report` is the generated JSON report path. Schema version `2` uses `kind: "suite_regression"`, records all five regression thresholds, and contains one entry per scenario with its verdict and findings.
- `summary` is the generated Markdown summary path. It contains the overall verdict, scenario table, regression details and active thresholds.
- `junit` is the generated JUnit XML path. It contains one testcase per scenario and maps RobotCI regressions to test failures.

This action intentionally does not manage baseline storage. Teams can initially keep known-good suite artifacts in their own CI/storage workflow; persistent baseline registries are a later RobotCI product layer.
