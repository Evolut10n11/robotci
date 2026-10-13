# Post-run acceptance: 13 October 2026

Completion tracking: [issue #99](https://github.com/Evolut10n11/robotci/issues/99).
This record verifies consumers of recorded evidence. It does not close M8,
claim a stable release, or replace a measured baseline/candidate experiment.

## Reference build and actual CI

RobotCI `0.1.0a1`; PR #100 head
`4df478bcf76e7f6f45fd219e4853cb6908e16bbd`, merged into main as
`3f1f080705429190a4caf3a038d4af2be65b714e`.
The merge and PR head have the same source tree:
`b0df70778a4a952100a3c63381b962a190c78dc9`.

All seven PR workflows completed successfully before merge:

| Check | Evidence |
| --- | --- |
| Core Windows/Ubuntu, Ruff, pytest, CLI/config | [CI run](https://github.com/Evolut10n11/robotci/actions/runs/38360638489) |
| Installed wheel | [Package Smoke](https://github.com/Evolut10n11/robotci/actions/runs/38360638453) |
| CI gate and report contract | [Suite Regression Gate Action](https://github.com/Evolut10n11/robotci/actions/runs/38360638287) |
| ROS setup | [ROS smoke](https://github.com/Evolut10n11/robotci/actions/runs/38360638446) |
| Loopback launch | [Nav2 Loopback Launch](https://github.com/Evolut10n11/robotci/actions/runs/38360638310) |
| Native navigation and opt-in MCP execution | [Navigation Suite](https://github.com/Evolut10n11/robotci/actions/runs/38360638320) |
| Docker navigation and opt-in MCP execution | [Docker Runtime](https://github.com/Evolut10n11/robotci/actions/runs/38360638383) |

The native and Docker archives each contain three PASS routes with matching
result/replay files. Their managed MCP run records each report `COMPLETED`,
`suite_status: PASS`, exit code 0, and no recorded worker cleanup error.
These are internal CI executions, not external-team pilots.

## Reproduce consumer acceptance

Install RobotCI in the active environment as in the [quickstart](../quickstart.md).
From the checkout, after a successful suite with recorded replays:

```powershell
python scripts/verify_postrun_acceptance.py --suite .robotci/suite-result.json
```

For the existing CI output layout:

```powershell
python scripts/verify_postrun_acceptance.py --suite artifacts/suite-result.json
```

The command works with the installed core package, without ROS, Docker or the
optional MCP SDK. It starts only a temporary loopback HTTP server on a free port.
Exit 0 emits a JSON acceptance report; exit 1 writes the failure to stderr and
emits no success JSON. Argument errors use argparse's exit 2. It does not change
exit codes of the underlying RobotCI commands it exercises.

All baseline stores, reports and deliberately modified controls live in an
isolated temporary directory and are removed afterward. Original suite, result
and replay bytes are hashed before/after; no original evidence is written.
The report is not a privacy-redacted support bundle: review it before sharing.

### Fourteen checks

The verifier validates suite/replay consistency and MCP scenario serialization;
captures a baseline and refuses accidental overwrite; exercises a self-comparison
PASS with JSON/Markdown/JUnit; serves the real session and bundled JS/CSS through
HTTP; checks MCP comparison serialization; forces one **synthetic** duration
regression and requires exit 4 plus all three reports; hides the resulting stale
replay; rejects inconsistent summaries and missing results with exit 3 and no new
reports; keeps the demo without an official gate; verifies baseline survival
after deleting its temporary source; and verifies unchanged original evidence.

A self-comparison is a consumer control, not an unchanged second simulation.
The duration intervention modifies a temporary JSON result and its matching suite
entry, not a controller. The report explicitly states `synthetic_controls: true`,
`new_simulation_executed: false`, `external_pilot_evidence: false`,
`browser_rendering_checked: false`, and `mcp_transport_checked: false`.
MCP serialization checks do not substitute for SDK/stdio/managed-runtime tests.

## Observed post-run results

The verifier was actually run on the downloaded native and Docker archives from
PR #100 using its unmodified wheel in a Python 3.13.5 sandbox. Preinstalled Python
dependencies were shared into the local virtual environment; this was not a
clean dependency-installation test. The supported Python 3.12 installation and
full repository checks are covered separately by the linked GitHub CI runs.

| Input | Routes | Consumer checks | Result |
| --- | ---: | ---: | --- |
| Native recorded suite | 3 | 14 | PASS |
| Docker recorded suite | 3 | 14 | PASS |

A separate native-vs-Docker suite comparison returned exit 3 with incompatible
runtime/environment fingerprints, rather than issuing a behavioral verdict.
Eight unit-test cases for the verifier also passed locally. Their fixtures are
explicitly synthetic, including both declared runtime variants, missing evidence,
inconsistent metadata, an escaping replay symlink, and a CLI timeout.

Archive SHA-256 digests were computed locally and matched GitHub artifact metadata:

| Artifact ID | Archive SHA-256 |
| --- | --- |
| `11793664875` (wheel) | `ae65c142869f6fed5bc53a1a3001131663607e1bbdd1bcc7a92dd5c007bff373` |
| `11795056504` (native) | `1e46489825d0dc0705f233a914b11db40189b9ce30cc25344ca59023e6fbb61e` |
| `11794688245` (Docker) | `a044e9365c0a013e97fed5c54aaa2aacff641c93ac2bba918df58a0cef2d577c` |

Source suite SHA-256 values:

- Native: `eb639f39cd3c8f8646996f7aa4a2e803eedf4d1e48fba4c0a4f2051a8be4934d`.
- Docker: `96da1b9dc0e8d25d21a6fda7e4ef7571d6f695033bf0cab309a1a0ef3e8da205`.

GitHub artifacts expire; these hashes identify the inspected inputs and do not
promise permanent download availability. No logs, maps or private source data
are copied into this document.

## Scope and remaining acceptance

The README, quickstart and .gitignore were checked against this workflow. Source
checkout requirements, Windows core vs Linux runtime, synthetic demo semantics,
and ignored local evidence remain explicit; .gitignore needs no cosmetic edit.
The Viewer UI workflow now also triggers for changes to this verifier/tests, so
frontend behavior tests, production build parity and viewer contract tests are
rechecked rather than inferred from an HTTP 200 response.

A browser-rendered interaction review and a newly measured, compatible
baseline/candidate controller intervention on the final release candidate are
not established by this post-run check. Prior measured Gazebo experiments remain
scoped to their own [runtime acceptance record](runtime-acceptance.md).
Gazebo/Clearpath, new adapters, physical-robot safety, hosted services and payment
claims are not expanded. Five external-team outcomes and the reviewed M8 decision
remain open under the [validation contract](README.md).
