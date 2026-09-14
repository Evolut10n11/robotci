# External pilot scorecard

Use this scorecard for issue #48 after a team has actually tried RobotCI on its own ROS2/Nav2 repository. The goal is to turn pilot conversations into comparable evidence instead of collecting unstructured opinions.

Do not record proprietary source code, maps, credentials, bag files, internal repository URLs, customer names that were not approved for publication, or production data. Use a neutral team identifier when necessary.

## One row per team

| Field | What to record |
| --- | --- |
| Team ID | `pilot-01` … `pilot-05` or an approved public name |
| Team profile | approximate engineering team size, robot type, simulator/runtime, GitHub usage |
| Setup outcome | PASS, BLOCKED, or ABANDONED |
| Setup time | rough active engineering minutes, excluding waiting time |
| Runtime used | native, Docker, or GitHub Actions |
| Real suite completed | yes/no + number of scenarios |
| Baseline saved | yes/no |
| Real candidate gated | yes/no |
| Regression found | yes/no; describe only the engineering category, not private code |
| Replay evaluated | yes/no/not applicable |
| Would use again | strong yes / yes / unsure / no |
| Highest-value problem | setup compatibility, regression gating, replay debugging, history, policies, collaboration, self-hosting, support, other |
| Paid signal | none / weak / medium / strong |
| Paid capability | exact capability behind the signal |
| Next action | follow-up, product fix, paid-pilot discussion, or stop |

## Product-use evidence

Check only what happened in the pilot, not what a team said it might do later.

- [ ] `robotci-init` was used on the team's repository.
- [ ] `robotci validate` completed or the blocker was captured.
- [ ] `robotci-doctor` or `robotci-support-bundle` produced a usable readiness result.
- [ ] At least one real navigation scenario ran.
- [ ] A successful suite was saved as a named baseline.
- [ ] A real code/config candidate was compared with the baseline.
- [ ] A regression gate result was reviewed by an engineer.
- [ ] Replay was inspected when it was relevant to debugging.
- [ ] The team stated whether it would put RobotCI into its normal workflow.

## Paid-signal rubric

Classify the strongest observed signal for each team.

### Strong

Use `strong` when there is a concrete buying motion, for example:

- asks to discuss a paid pilot, quote, procurement path, or budget;
- requests a self-hosted/team deployment with support;
- says a named feature is required for adoption and confirms budget or purchasing authority exists;
- asks how pricing would work for a real team rollout.

### Medium

Use `medium` when the pain is concrete and recurring but money has not yet entered the conversation, for example:

- asks for shared baseline/history retention across engineers;
- wants organization-level policy gates or PR reports;
- needs private replay/artifact retention or self-hosted control;
- explicitly says the team would adopt RobotCI if one team feature existed.

### Weak

Use `weak` for interest without a demonstrated workflow commitment, for example:

- likes the concept but did not complete a real candidate gate;
- asks to be kept informed;
- says a team feature would be useful without committing to repeated use.

### None

Use `none` when the pilot does not reveal repeat-use intent or a meaningful team problem RobotCI can solve.

## Quantitative cohort summary

After all five pilots, fill this table from the individual scorecards.

| Metric | Target | Actual |
| --- | ---: | ---: |
| Teams recruited | 5 | |
| Teams completing a real suite | >= 3 | |
| Teams completing baseline vs candidate gate | >= 2 | |
| Teams saying they would use the gate again | >= 2 | |
| Teams with medium-or-strong paid signal | >= 1 | |
| Teams with strong paid signal | >= 1 preferred | |

Also record median setup time for teams that reached a real suite. A tool that requires extensive founder intervention may show technical success without product readiness.

## Decision matrix

Choose the smallest next investment supported by repeated evidence.

| Repeated evidence | Next product investment |
| --- | --- |
| Teams fail before first suite | onboarding/runtime compatibility |
| Suites run but gates are noisy | stronger deterministic statistics/policies |
| Gates find regressions but debugging is slow | baseline-vs-candidate replay comparison |
| Multiple engineers need the same known-good state | persistent shared baseline registry |
| Teams want trends/auditability across PRs | hosted or self-hosted run history |
| Teams need centralized enforcement | team policy gates / GitHub integration |
| Enterprise teams cannot send artifacts externally | self-hosted control plane + support |
| No repeated use and no paid signal | stop adding platform features; revisit core problem/segment |

Do not start generic SaaS authentication, billing, organization management, or a cloud control plane solely because they appear on the long-term roadmap.

## Five-team rollup

Copy one line per pilot after evidence is collected.

| Team | Real suite | Candidate gate | Repeat-use intent | Paid signal | Highest-value next step |
| --- | --- | --- | --- | --- | --- |
| pilot-01 | | | | | |
| pilot-02 | | | | | |
| pilot-03 | | | | | |
| pilot-04 | | | | | |
| pilot-05 | | | | | |

## Final pilot decision

At the end of the cohort, write exactly one primary decision:

- **Invest** — evidence supports one specific paid/team capability; open a narrowly scoped product issue.
- **Improve core** — teams value RobotCI but setup, compatibility, gating quality, or replay blocks repeated use.
- **Change segment** — the workflow works technically but the tested team profile has weak pain or weak willingness to adopt.
- **Stop / defer** — repeated real usage and paid-layer signal did not materialize.

The decision should cite observed pilot counts and behavior, not enthusiasm or feature requests alone.
