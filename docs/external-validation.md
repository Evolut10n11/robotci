# External validation pilot

RobotCI is ready for a narrow external validation phase before any hosted backend, authentication, billing, or multi-tenant infrastructure is built.

The purpose of this pilot is not to collect stars or generic feedback. It is to answer one commercial question:

> Will a real ROS2/Nav2 team use RobotCI on its own repository, compare a known-good baseline against a real change, and value the result enough to ask for persistent history, collaboration, hosted reports, or support?

## Target cohort

Recruit exactly 5 teams that match most of these criteria:

- ROS2 + Nav2 is used in active development;
- the team has 3–30 robotics/software engineers;
- a simulator or headless navigation environment already exists;
- changes are reviewed in GitHub pull requests;
- navigation regressions are currently discovered through manual simulation, field testing, or post-merge debugging;
- the team can run one safe simulation-only scenario without giving RobotCI access to production robots or secrets.

Avoid broad outreach to generic robotics communities during the first pilot. Five relevant teams with concrete workflows are more useful than fifty low-intent signups.

## What each pilot team should complete

A pilot counts as technically completed only when the team performs the following on its own repository:

1. Install RobotCI in a development environment.
2. Run `robotci-init` and adapt the generated `robotci.yaml` to one safe simulation route.
3. Run `robotci validate`, `robotci doctor`, and a successful `robotci run`.
4. Save that successful suite as a known-good baseline with `robotci-baseline save`.
5. Make or select a real navigation/configuration change.
6. Run the candidate suite again.
7. Gate it with `robotci-baseline gate` or the reusable GitHub Action.
8. Inspect the regression report and, when relevant, the replay viewer.

The preferred first-session path is:

```bash
robotci-init
robotci validate
robotci doctor
robotci run
robotci-baseline save pilot-main --suite .robotci/suite-result.json

# make or checkout a real navigation/configuration change
robotci run
robotci-baseline gate pilot-main --candidate .robotci/suite-result.json
```

Do not ask pilot teams to deploy to hardware merely to test RobotCI. The initial validation should remain simulation-only.

## Evidence to collect

For each team, record the following facts rather than relying on impressions:

| Signal | What to capture |
| --- | --- |
| Setup completion | Did `validate`, `doctor`, and the first suite complete? |
| Time to first useful result | Minutes from installation to first baseline or blocker |
| Real repository | Was this their own project rather than the RobotCI demo? |
| Real change | Did they compare an actual code/config change? |
| Regression usefulness | Did RobotCI find, confirm, or rule out a behavior regression? |
| CI adoption | Did they put the gate in a PR workflow? |
| Replay usefulness | Did visual replay reduce debugging time or clarify a metric delta? |
| Repeated use | Did they run RobotCI again without assistance? |
| Paid signal | Did they ask for history, shared baselines, hosted reports, policy management, self-hosting, or support? |

Do not collect proprietary maps, robot source code, credentials, bag files, or full simulation artifacts unless a team explicitly chooses to share them. Compact metrics, error text, and redacted screenshots are sufficient for the pilot.

## Interview questions

Ask these after the team has actually used the product. Avoid asking hypothetical pricing questions before they have a concrete result.

1. How do you detect navigation regressions today?
2. What is the most expensive recent regression that reached simulation, staging, or hardware?
3. At which step did RobotCI require the most manual work?
4. Was the PASS/REGRESSION verdict trustworthy enough to use in code review? Why or why not?
5. Which metric or report was most useful? Which one was noise?
6. Would you block a merge on this gate today? What would have to change first?
7. Would your team benefit from shared baseline history across branches, robots, or releases?
8. Would hosted PR reports be acceptable, or must all artifacts stay inside your network?
9. Who would own this tool internally: robotics, platform/DevEx, QA, or another team?
10. If RobotCI removed a recurring manual regression workflow, what budget would it compete with: engineering time, CI tooling, QA infrastructure, or support?
11. What feature would make you ask to keep using RobotCI next month?
12. Would you be willing to discuss a paid Team or self-hosted pilot if persistent history and team policies existed?

The last question is the main commercial signal. A polite "nice project" is not validation; willingness to continue a paid discussion is.

## Success criteria

The first cohort is successful when, out of 5 teams:

- at least 3 complete a real navigation suite on their own repository;
- at least 2 compare a real baseline against a real candidate change;
- at least 2 say they would use the gate again in normal development;
- at least 1 asks for a paid-layer capability strongly enough to discuss a Team/self-hosted pilot.

If fewer than 3 teams complete the first suite, prioritize onboarding/runtime compatibility before building commercial infrastructure.

If teams complete suites but do not care about regression history or gating, revisit the product wedge before building a hosted backend.

If at least one team asks for persistent shared history, policies, or hosted/self-hosted reporting, the next implementation should be the smallest service needed to support that exact request.

## Pilot tracker

Keep one row per team. Do not store secrets or proprietary technical details here.

| Team | ROS2/Nav2 fit | First suite | Baseline compare | CI gate | Replay used | Repeated use | Paid signal | Main blocker |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Team 1 | pending | pending | pending | pending | pending | pending | pending | pending |
| Team 2 | pending | pending | pending | pending | pending | pending | pending | pending |
| Team 3 | pending | pending | pending | pending | pending | pending | pending | pending |
| Team 4 | pending | pending | pending | pending | pending | pending | pending | pending |
| Team 5 | pending | pending | pending | pending | pending | pending | pending | pending |

## Decision after the pilot

Use the evidence to choose exactly one next direction:

- **Onboarding problems dominate:** improve installation, runtime adapters, diagnostics, and example configuration.
- **Regression signal is weak:** improve deterministic metrics, repeated-run statistics, and false-positive handling.
- **Replay is the strongest value:** prioritize baseline-vs-candidate visual comparison and divergence navigation.
- **Teams ask for shared history/policies:** build the minimal paid Team service around compact run summaries and persistent baselines.
- **Private-network requirements dominate:** validate a self-hosted control-plane model before a public SaaS.
- **No strong repeated-use or paid signal:** change the product direction before investing in cloud infrastructure.

The pilot is complete when there is enough evidence to make one of those decisions, not when all five teams say something positive.