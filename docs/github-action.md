# RobotCI GitHub regression gate

RobotCI can be used directly as a composite GitHub Action. The action compares a candidate navigation result with a known-good baseline and fails the job when the configured regression policy is exceeded.

## Example

```yaml
name: Navigation regression

on:
  pull_request:

jobs:
  regression:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v4

      # Produce or download baseline.json and candidate.json before this step.
      - name: Block navigation regressions
        id: robotci
        uses: Evolut10n11/robotci@main
        with:
          baseline: artifacts/baseline.json
          candidate: artifacts/candidate.json
          report: artifacts/regression-report.json
          max-duration-increase-pct: "10"
          max-path-length-increase-pct: "10"
          max-stuck-events-increase: "0"
          max-recoveries-increase: "0"

      - name: Upload regression report
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: robotci-regression-report
          path: artifacts/regression-report.json
```

The action installs the RobotCI version from the referenced repository revision, runs `robotci compare`, and writes the versioned machine-readable report. A regression returns RobotCI exit code `4`, which makes the action step fail and therefore makes it suitable as a required pull-request check.

For reproducible production use, pin the action to a release tag or commit SHA rather than `main`.

## Inputs

| Input | Default | Meaning |
| --- | --- | --- |
| `baseline` | required | Known-good scenario result JSON |
| `candidate` | required | Candidate scenario result JSON |
| `report` | `artifacts/regression-report.json` | Generated report path |
| `max-duration-increase-pct` | `10` | Allowed duration increase (%) |
| `max-path-length-increase-pct` | `10` | Allowed path-length increase (%) |
| `max-stuck-events-increase` | `0` | Allowed additional stuck events |
| `max-recoveries-increase` | `0` | Allowed additional recoveries |

## Output

`report` is the path passed to the action for the generated JSON report. The report is written before RobotCI returns the regression exit code, so callers can upload it with `if: always()` even when the gate blocks the pull request.
