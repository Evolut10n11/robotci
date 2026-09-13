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
- JUnit/JSON artifacts
- GitHub Actions examples

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

- Open source: local CLI and regression engine.
- Team: hosted history, GitHub PR reports and team policies.
- Enterprise later: self-hosted control plane, SSO, auditability, retention and support.

The first paid signal should be a team willing to pay for persistent history + PR gating, not stars or downloads.

## Product milestones

### P0 — trustworthy regression engine

Required before selling anything:

- collect navigation metrics reliably
- baseline vs candidate comparison
- configurable thresholds
- distinct `REGRESSION` verdict
- deterministic JSON report
- tests for edge cases and corrupted/incomplete baselines

### P1 — excellent GitHub experience

- GitHub Actions reusable example
- Markdown PR summary artifact
- JUnit output
- easy baseline generation/update flow
- one-command onboarding for an existing Nav2 repository

### P2 — external validation

Find 5 external ROS2/Nav2 teams and ask them to run RobotCI on a real repository.

Success signal:

- at least 3 complete a real navigation suite
- at least 2 use baseline comparison on a real change
- at least 1 asks for history, collaboration, hosted reports, or support strongly enough to discuss payment

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

The next feature after runtime metrics is M4 baseline comparison.

A candidate run should be compared scenario-by-scenario with a baseline using metrics such as:

- duration
- path length
- distance to goal
- stuck events
- recoveries

The comparison layer must stay ROS-independent so it can be unit-tested on Windows and used by both local and hosted versions later.

## What not to build yet

- generic robotics cloud
- custom simulator
- Kubernetes control plane
- multi-tenant dashboard before external validation
- support for every ROS distro
- AI-generated explanations before deterministic regression data is trustworthy

## North-star outcome

A robotics engineer opens a pull request and, before touching a physical robot, sees:

> 11/12 scenarios are stable. `warehouse_long_route` regressed: path +18%, duration +24%, two new stuck events. Merge blocked.

That is the moment RobotCI stops being a pet project and becomes a product.
