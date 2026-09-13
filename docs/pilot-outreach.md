# Pilot outreach kit

This document turns the external validation pilot into a repeatable recruitment workflow. The goal is to find a small number of ROS2/Nav2 teams that have a real regression problem and are willing to try RobotCI on their own repository.

Do not optimize for stars, broad community reach, or generic robotics interest. Optimize for qualified teams that can complete one real baseline-to-candidate comparison.

## Ideal pilot profile

Prioritize teams that match most of the following:

- actively develop with ROS2 and Nav2;
- have 3–30 robotics/software engineers;
- already use GitHub pull requests;
- have a simulator, recorded scenario, or headless navigation environment;
- regularly change planners, controllers, maps, costmaps, localization, navigation parameters, or robot software that can affect motion behavior;
- currently catch regressions through manual simulation, QA sessions, field testing, or post-merge debugging;
- can run a simulation-only pilot without exposing production credentials or proprietary robot infrastructure.

Deprioritize teams that only experiment with ROS2 tutorials, do not have repeatable navigation scenarios, or cannot run any representative simulation outside production hardware.

## Where to find teams

Use targeted, high-signal sources first:

1. GitHub repositories with active ROS2/Nav2 development and recent pull requests.
2. Companies and university labs that publicly mention Nav2, ROS2 autonomy, AMRs, delivery robots, service robots, warehouse robotics, or autonomous mobile platforms.
3. Existing professional contacts who work in robotics, autonomy, QA, simulation, DevEx, or platform engineering.
4. ROS/robotics community discussions only when a concrete regression or CI problem is visible.

Do not scrape or mass-message large lists. Five high-quality conversations are the objective.

## Qualification checklist

Before contacting a team, record only public, non-sensitive facts:

- organization/project name;
- public repository or company page;
- evidence of ROS2/Nav2 usage;
- evidence of active development;
- likely simulation/test environment;
- likely owner of the problem: robotics engineer, autonomy lead, QA, DevEx, or platform engineer;
- one concrete reason RobotCI may be relevant.

A team is qualified when there is a plausible path to this workflow:

```text
existing navigation scenario
        ↓
known-good RobotCI baseline
        ↓
real code/config change
        ↓
RobotCI candidate run
        ↓
PASS / REGRESSION evidence in code review
```

## First contact

Keep the first message short and specific. Do not lead with pricing or a long product pitch.

### GitHub / community message

> Hi — I’m building RobotCI, a local-first regression testing tool for ROS2/Nav2. I noticed your project actively works with navigation changes, and I’m looking for a few teams to test a real baseline-vs-candidate workflow on their own simulator/repository. The pilot is simulation-only and does not require sharing source code, maps, credentials, or robot access. If navigation regressions currently take manual simulation or field time to catch, I’d be interested in helping you try one representative scenario and seeing whether the regression gate is actually useful.

### Direct professional message

> Hi! I’m validating RobotCI with a small number of ROS2/Nav2 teams. It turns a repeatable navigation scenario into a known-good baseline and then checks later changes for behavior regressions in local/CI runs. I’m specifically looking for teams that already spend time manually checking navigation changes. The pilot stays simulation-only and private; I don’t need access to proprietary code or robot credentials. Would you be open to testing one real scenario and giving feedback after using it?

Do not send repeated follow-ups to people who show no interest. One concise follow-up is enough.

## Qualification call

A short call or chat should establish whether there is a real problem before investing setup time.

Ask:

1. How do you currently catch navigation regressions?
2. Which changes most often cause unexpected navigation behavior?
3. Do you have a repeatable simulator/headless scenario today?
4. Is navigation validation part of PR review, nightly CI, or mostly manual?
5. What was the last regression that cost meaningful engineering or robot time?
6. Can one representative scenario run without production hardware or secrets?

Proceed when the team has both a repeatable scenario and a real regression cost. If neither exists, politely stop the pilot rather than forcing a weak fit.

## Pilot invitation

When a team qualifies, send the concrete scope:

> The pilot is one real navigation workflow, not a demo repository. We’ll get one scenario running, save a known-good baseline, compare one real change, and inspect the result in CI/replay where useful. The first session should stay under roughly one focused engineering session. RobotCI remains local to your environment unless you explicitly choose to share logs or screenshots. The main thing I need afterward is candid feedback on setup friction, trust in the verdict, whether you would run it again, and whether shared history/policies/hosted or self-hosted reporting would solve a real team problem.

## Evidence tracker

Use one row per qualified team. Store only non-sensitive information.

| Team | Source | ROS2/Nav2 evidence | Problem owner | Current regression workflow | Qualified | Contacted | Replied | Pilot scheduled | First suite | Baseline compare | Repeated use | Paid signal | Main blocker |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Team 1 | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending |
| Team 2 | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending |
| Team 3 | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending |
| Team 4 | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending |
| Team 5 | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending |

## Funnel metrics

Track the funnel rather than relying on anecdotal interest:

- qualified teams found;
- qualified teams contacted;
- response rate;
- qualification-to-pilot rate;
- pilot start rate;
- first-suite completion rate;
- baseline comparison completion rate;
- repeated-use rate;
- number of concrete paid-layer requests.

Do not treat a positive reply as validation. The strongest progression is:

```text
qualified problem
→ real repository setup
→ baseline/candidate comparison
→ repeated use
→ request for team capability
→ willingness to discuss paid pilot
```

## Paid-signal classification

Classify commercial signals consistently.

### Weak

- “cool project”;
- willingness to star or share it;
- hypothetical interest in a dashboard;
- generic request for more features without repeated use.

### Medium

- asks for shared baselines or historical runs;
- asks for GitHub organization/team support;
- asks for policy configuration or richer PR reports;
- asks whether a self-hosted version exists;
- wants help rolling it out to additional repositories.

### Strong

- requests a concrete Team/self-hosted pilot;
- identifies an internal buyer or budget owner;
- asks for security/deployment requirements to start procurement;
- offers to pay for support, rollout, hosted history, policies, or private deployment;
- asks for a proposal, trial terms, or implementation timeline.

Build the next commercial feature only around repeated medium/strong signals, not guesses.

## Stop conditions

Do not keep adding SaaS infrastructure merely because the pilot is slow.

Pause and revisit the wedge if:

- fewer than 3 of 5 qualified teams can complete a first suite;
- teams consistently lack repeatable scenarios;
- verdicts are not trusted enough for code review;
- nobody repeats the workflow after assisted setup;
- no team asks for collaboration/history/policy/self-hosted capabilities after real use.

If setup friction dominates, improve onboarding/runtime adapters. If replay is repeatedly the strongest value, focus on baseline-vs-candidate visual debugging. If persistent history and team policy repeatedly appear, that is the strongest path toward a paid product layer.
