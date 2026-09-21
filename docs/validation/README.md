# M8 execution and evidence

M7 shipped `0.1.0a1`. M8 remains open until five external-team outcomes have been
reviewed and a product direction has been chosen under [issue #48](https://github.com/Evolut10n11/robotci/issues/48).
No team has been enrolled in the checked-in register. All five slots are pending.
The public [shortlist](../pilot-targets.md) contains prospects, not participants.

## Current work

- [Clearpath preflight](clearpath-preflight.md): source inspection and RobotCI
  onboarding in a separate public checkout; simulation is blocked by missing ROS
  and Docker in the execution environment. This is internal evidence only.
- [cohort.json](cohort.json): five empty slots for actual external participants.
- `scripts/pilot_report.py`: standard-library-only evidence validation and a
  JSON/Markdown summary, runnable on Windows or Linux from the RobotCI checkout.
- [Scorecard](../pilot-scorecard.md) and the public alpha feedback form: interview
  details, actual usage, repeat-use intent, and explicit paid-pilot willingness.

## Execute one pilot

1. Obtain a team's agreement to a simulation-only session. Confirm its own Nav2
   workflow, problem owner, and one real scenario using the [qualification checklist](../pilot-targets.md).
   Outreach requires Ivan's authorization; this change sends no messages.
2. Assign one neutral, stable `team_id` to that team, set its slot to `active`, and
   keep identifying/contact details outside the public repository. Several repos
   belonging to the same team occupy one slot.
3. Follow the [quickstart](../quickstart.md) and [external adapter contract](../native-runtime-adapter.md).
   Record installation/configuration, readiness, a real suite, baseline capture,
   and a candidate gate. A Loopback demo on our machine does not count.
4. Capture the gate outcome and whether the engineer trusts or finds it useful.
   `PASS` and `REGRESSION` can both be useful, completed comparisons. An invalid
   input, incompatible fingerprint, `INFRA_ERROR`, or unexecuted gate is not a
   completed comparison. Keep failed attempts and blockers in the scorecard.
5. Ask the repeat-use and paid-pilot questions after actual use. Record a negative
   answer as `false`, and an unasked/unanswered question as `null`. Feature interest
   alone is not willingness to discuss payment. Actual unassisted reuse is a
   separate scorecard observation; do not infer it from intent.
6. Complete the scorecard (including report/replay usefulness or not applicable),
   update the register, and regenerate the summary. If blocked, collect the
   [support bundle](../support-bundle.md), review/redact it before sharing, and
   record the exact failing step and next action.

Do not upload private repositories, maps, robot code, full logs, credentials,
customer names, or personal contact information. A neutral session-note ID or an
approved public issue URL is sufficient as an evidence reference.

## Register contract

`schema_version` is integer `1`. There must be exactly five unique slots,
`pilot-01` through `pilot-05`. A pending slot has `team_id`, `setup_minutes`,
`blocker`, and all evidence entries set to `null`. Never fill missing observations
with synthetic success or with results from our own preflight.

For an enrolled team, each observed signal replaces `null` with an object containing:

| Field | Meaning |
| --- | --- |
| `outcome` | JSON boolean: observed yes or observed no |
| `observed_on` | ISO calendar date `YYYY-MM-DD` of the observation |
| `reference` | Nonempty, redacted evidence reference; no private URL required |

All five evidence keys must remain present:

| Signal | Evidence needed for `true` |
| --- | --- |
| `own_repo_suite` | The participant completed a successful navigation suite on its own repository, with current result/telemetry evidence |
| `baseline_saved` | That successful suite was accepted by `robotci-baseline save` |
| `real_candidate_gate` | A real code/config change was compared with that baseline using a compatible, completed gate |
| `reuse_intent` | After actual use, the team explicitly says it would use the gate again in normal development |
| `paid_discussion` | After actual use, the team names a capability/problem and explicitly agrees to discuss a paid pilot |

The validator requires suite evidence before positive baseline, reuse, or payment
claims, and a saved baseline before a positive candidate claim. It rejects
duplicate teams (case/outer whitespace ignored), duplicate JSON keys, unknown
fields/versions, undated observations, and invalid numeric measurements.

States: `active` means work is ongoing; `completed` means all five interview/use
outcomes have been recorded, including negative ones. It does not mean technical
success. `blocked` and `withdrawn` are terminal outcomes for this round and require
a reason in `blocker`; unknown observations can stay null. If work resumes, return
the slot to `active`. Keep the failed attempt in the scorecard. Do not replace a
failed participant with a successful one to improve the cohort's counts.

`setup_minutes` is optional active engineering time to the first useful result or
blocker, excluding waiting time. The median includes only teams with a successful
real suite and a recorded time; the report also gives that sample size.

## Generate the report

From the RobotCI checkout, these commands work in PowerShell and Bash:

```powershell
python scripts/pilot_report.py docs/validation/cohort.json
python scripts/pilot_report.py docs/validation/cohort.json --format json
```

Exit `0` means the register is structurally valid, even if every slot is empty.
Exit `2` means invalid input; diagnostics go to stderr and no success report is
emitted. Do not use the exit code as a product or robot quality gate.

`AWAITING_EVIDENCE` means at least one slot is pending/active.
`READY_FOR_REVIEW` means all five outcomes are recorded as completed, blocked, or
withdrawn. Independently, `criteria_met` requires 5 enrolled teams, 3 real suites,
2 real candidate gates, 2 repeat-use intentions, and 1 explicit paid discussion.
Negative evidence can justify a decision even if the success criteria are not met.

The tool checks human-recorded claims for consistency; it does not fetch evidence,
verify participant identity, authenticate reports, or prove the linked experiment
actually happened. Review source observations before making a product decision.

## Close M8

Once the cohort has been reviewed, record one dated decision in a focused issue
or document: invest in one named capability, improve core, change segment, or
stop/defer. Cite counts, evidence references, setup friction, the strongest
blockers, and the owner/next action. Link that decision from issue #48 before
marking M8 complete. Neither this preparatory PR nor `criteria_met=true` closes M8
automatically. A paid signal does not authorize spending, outreach, or deployment.
