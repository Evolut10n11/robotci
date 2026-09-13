# RobotCI product direction

RobotCI should stay useful as an open-source ROS2/Nav2 regression-testing CLI while developing a paid layer around the parts that become painful for teams: storing baselines, comparing runs across commits, explaining regressions, and enforcing release gates across multiple robots and repositories.

This document is a product hypothesis, not a promise to build a SaaS before users ask for it.

## Problem worth paying for

Robotics teams can have passing unit tests while navigation behavior quietly gets worse. A planner/controller/configuration change may still reach the goal but take a longer path, require more recoveries, get stuck more often, or become less reliable.

The commercial problem is therefore not “run ROS in CI”. It is:

> Tell me whether this pull request made robot behavior worse, show me why, and stop the release before it reaches hardware.

## Initial customer profile

Start narrow:

- teams using ROS2 + Nav2
- 3–30 robotics/software engineers
- simulation already exists or can run headlessly
- GitHub-based development
- navigation changes are reviewed through pull requests
- regressions are currently found by manual simulation, field testing, or after merge

Avoid trying to support every robotics stack at the beginning.

## Open-source core

The free CLI should remain strong enough to earn trust:

- repeatable scenarios
- YAML configuration
- native and Docker execution
- machine-readable results
- navigation metrics
- local baseline comparison
- regression verdict and non-zero exit code
- suite-level regression gating
- JSON, Markdown, and JUnit reports
- reusable GitHub Action / PR gate
- local named-baseline capture and gating
- one-command local onboarding
- replay and visualization as the next major developer-facing layer

A team must be able to prove RobotCI is useful before paying us.

## Paid wedge

A future Team/Pro layer can sell coordination and history rather than hiding the core runner behind a paywall.

Candidate paid capabilities:

1. Persistent baseline registry per robot / branch / release.
2. Pull-request regression report with metric deltas and scenario-level explanation.
3. Historical trend dashboard for path length, completion time, stuck events and recoveries.
4. Policy gates such as “block merge when path length regresses > 10% on two scenarios”.
5. Flaky-run detection using repeated executions and confidence thresholds.
6. Team projects, private baseline storage and retention controls.
7. Self-hosted runner / private-network support for companies that cannot upload robot artifacts.
8. Notifications and integrations after the GitHub workflow is proven.

## Monetization hypothesis

Do not optimize pricing before validating demand. A simple hypothesis to test with real users:

- Open source: local CLI, regression engine, reports, replay, and CI gate.
- Team: hosted history, GitHub PR reports, persistent baselines, and team policies.
- Enterprise later: self-hosted control plane, SSO, auditability, retention and support.

The first paid signal should be a team willing to pay for persistent history + PR gating, not stars or downloads.

## Current product status

The deterministic regression foundation and the first local usability layer are now largely implemented:

```text
scenario execution           ✅
configuration                ✅
runtime navigation metrics   ✅
baseline/candidate compare    ✅
REGRESSION exit semantics    ✅
machine-readable JSON report ✅
suite-level regression gate  ✅
reusable GitHub Action       ✅
Markdown PR summary          ✅
JUnit report                 ✅
local baseline capture UX     ✅
named baseline candidate gate ✅
one-command onboarding        ✅
CI runtime path filtering     ✅
3D replay/viewer              🚧
external team validation      🚧
```

The next work should finish the developer-facing replay flow and prove demand with real teams rather than inventing cloud infrastructure early.

## Product milestones

### P0 — trustworthy regression engine ✅

Implemented:

- navigation metrics
- baseline vs candidate comparison
- configurable thresholds
- distinct `REGRESSION` verdict
- deterministic versioned JSON reports
- edge-case validation and tests
- suite-level comparison/gating

P0 should still be hardened as new real-world cases appear, but it is no longer the main missing product layer.

### P1 — excellent GitHub experience 🚧

Implemented:

- reusable GitHub Action
- Markdown regression summary
- JUnit output
- strict JSON artifacts
- suite-level PR/release gate
- self-contained local baseline capture with explicit replace semantics
- `robotci-baseline gate <name> --candidate ...`
- `robotci-init` for a valid starter `robotci.yaml`
- path-aware CI so docs, web, and baseline-only changes do not pay the full ROS/Nav2/Docker runtime cost

Remaining high-value work:

- replay/viewer integration so a developer can move from a failed gate to the exact behavior visually
- baseline-vs-candidate visual comparison and divergence navigation after the basic viewer flow is stable

### P2 — external validation 🚧

P2 is active and tracked in issue #48. The execution/interview playbook lives in `docs/external-validation.md`.

Find 5 external ROS2/Nav2 teams and ask them to run RobotCI on a real repository.

Success signal:

- at least 3 complete a real navigation suite
- at least 2 use baseline comparison on a real change
- at least 2 say they would use the gate again in normal development
- at least 1 asks for history, collaboration, hosted reports, policies, self-hosting, or support strongly enough to discuss payment

If those signals do not appear, change the product direction before building a cloud backend.

### P3 — minimal paid service

Only after P2:

- organization/project model
- API token or GitHub App authentication
- upload compact run summaries, not full simulation data by default
- baseline/history storage
- PR report and regression gate
- simple billing

## Near-term engineering priority

Two tracks can proceed without coupling to each other:

1. **Developer experience:** finish visual replay / `robotci view`, then baseline-vs-candidate visual comparison.
2. **External validation:** run the five-team pilot and fix only evidence-backed onboarding, runtime-compatibility, diagnostics, or report problems that block real adoption.

Do not add a generic backend merely because the open-source core is becoming feature-complete. The next non-viewer engineering work should come from real pilot friction unless it is a clear correctness or maintainability issue.

A candidate run should continue to be compared scenario-by-scenario with a baseline using deterministic metrics such as:

- duration
- path length
- distance to goal
- stuck events
- recoveries

The comparison layer must stay ROS-independent so it can be unit-tested on Windows and reused by local and future hosted versions.

## What not to build yet

- generic robotics cloud
- custom simulator
- Kubernetes control plane
- multi-tenant dashboard before external validation
- support for every ROS distro
- AI-generated verdicts
- billing/auth before external teams demonstrate demand

AI explanations may be added later, but only above the deterministic regression engine; they must not become the source of truth for PASS/FAIL/REGRESSION.

## North-star outcome

A robotics engineer opens a pull request and, before touching a physical robot, sees:

> 11/12 scenarios are stable. `warehouse_long_route` regressed: path +18%, duration +24%, two new stuck events. Merge blocked.

Then the engineer opens the replay and jumps directly to the moment where candidate behavior diverged from the baseline.

That is the moment RobotCI stops being a pet project and becomes a product.
