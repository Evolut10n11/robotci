# RobotCI roadmap

[Project overview](../README.md) · [Product direction](product.md)

The current release is public alpha `0.1.0a1`. Status describes shipped
capabilities and remaining scope; milestone numbers do not imply every later
capability is absent until earlier product validation finishes.

| Milestone | Status | Scope |
| --- | --- | --- |
| M0 · Vertical slice | Complete | Headless A-to-B navigation and a result artifact |
| Runtime portability | Complete for the current stack | Windows core, Ubuntu native, Docker, and GitHub Actions |
| M1 · Scenario suites | Complete | Multiple configured scenarios and suite summaries |
| M2 · Configuration | Complete | Strict YAML validation and consistent project resolution |
| M3 · Metrics | Complete | Duration, path length, goal distance, stuck events, recoveries, and telemetry quality |
| M4 · Regression | Complete | Baseline/candidate comparison and deterministic REGRESSION verdicts |
| M5 · Reproducibility | Complete for the current contract | Versioned execution identity and compatible runtime provenance |
| M6 · CI integration | Complete | Action, blocking gate, JSON/Markdown/JUnit, summaries and artifacts |
| M7 · Public alpha | Complete | `0.1.0a1`, quickstart, example, wheel smoke, and feedback forms |
| M8 · Validation | In progress | Five external teams, observed outcomes, and a reviewed product decision |
| M9 · Visual replay | Partially implemented | Recorder/viewer exist; finish controls, source integration, and baseline/candidate replay |
| M10 · Robot adapters | Planned | First non-Nav2 backend; evaluate Unitree Go2 + MuJoCo |
| M11 · MCP / agent API | Partially implemented | Six read-only tools exist; execution/cancellation and reference agent remain planned |
| M12 · Team product validation | Planned, evidence-gated | Shared baselines/history and narrowly scoped paid experiments |

## Current focus

1. Collect real M8 evidence under [issue #48](https://github.com/Evolut10n11/robotci/issues/48).
   Use the [register](validation/README.md); internal demo runs and repository
   inspections do not count as external participation.
2. Fix demonstrated onboarding/runtime blockers. The
   [Clearpath preflight](validation/clearpath-preflight.md) identifies the need for
   a simulation environment and an explicit namespace-aware integration.
3. Finish replay in the existing GUI workstream, then use observed debugging
   needs to scope baseline/candidate visual comparison.

## Completion evidence

| Milestone | Implementation record |
| --- | --- |
| M3 | [PR #75](https://github.com/Evolut10n11/robotci/pull/75) |
| M4 | [PR #76](https://github.com/Evolut10n11/robotci/pull/76) |
| M5 | [PR #77](https://github.com/Evolut10n11/robotci/pull/77) |
| Application API and CLI | [PR #78](https://github.com/Evolut10n11/robotci/pull/78), [PR #79](https://github.com/Evolut10n11/robotci/pull/79) |
| Read-only MCP | [PR #80](https://github.com/Evolut10n11/robotci/pull/80) |
| M6 | [PR #81](https://github.com/Evolut10n11/robotci/pull/81) |
| M7 | [PR #82](https://github.com/Evolut10n11/robotci/pull/82) |
| M8 preparation | [PR #83](https://github.com/Evolut10n11/robotci/pull/83); milestone remains open |

New adapters, hosted infrastructure, and paid services depend on an observed use
case. Agents may explain evidence; regression decisions remain deterministic.
