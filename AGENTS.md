# RobotCI Agent Guidelines

Read this file and `README.md` before choosing work.

## Mission

RobotCI is deterministic behavior CI for robots. The core product loop is:

```text
code/config change
-> run repeatable robot scenarios
-> collect deterministic telemetry
-> compare candidate with known-good baseline
-> emit PASS / FAIL / TIMEOUT / INFRA_ERROR / REGRESSION
-> block unsafe changes before physical-robot testing
```

The project is Nav2-first, not Nav2-only. Future adapters may include MuJoCo, Unitree, Gazebo and Isaac-based runtimes, but all of them should normalize into stable RobotCI result/replay contracts.

## Source of truth

Use these layers deliberately:

- `README.md`: product vision and roadmap.
- `AGENTS.md`: operating rules for coding agents.
- `.agent/STATE.md`: machine-local handoff/state; never commit it.
- Git history / PRs / CI: durable implementation state.
- GitHub issue #18 `Agent Coordination`: cross-agent coordination mailbox.

Before significant work, inspect `git status`, current branch, latest `main`, open PRs and issue #18. Never duplicate work already owned by another agent or active PR.

## Current architecture rules

1. Keep the cross-platform Python core independent from ROS imports.
2. Keep ROS-specific code under `robotci/ros/` or runtime adapters.
3. `INFRA_ERROR` is distinct from robot-behavior `FAIL`.
4. Regression verdicts are deterministic. LLMs may explain or diagnose them but must not decide PASS/FAIL/REGRESSION.
5. Prefer stable, versioned JSON contracts between layers.
6. Simulator/backend-specific code should produce normalized RobotCI results rather than leak into consumers such as the GUI.
7. Prefer small tested vertical slices over large speculative rewrites.
8. Preserve Windows core development even when runtime execution requires Linux/ROS.

## Current product priorities

Work roughly in this order unless issue #18 assigns otherwise:

1. Stable deterministic runtime execution and telemetry.
2. Baseline/candidate comparison and suite-level regression reports.
3. CI/release gating and reusable integration surfaces.
4. Replay artifacts and 3D visualization.
5. Baseline-vs-candidate visual replay.
6. Additional robot/simulator adapters, with Unitree Go2 + MuJoCo as a likely first non-Nav2 target.
7. MCP/tool APIs and LangGraph/LangChain orchestration.
8. Persistent team baselines/history and other monetizable collaboration features.

Do not skip unfinished foundations to start Unitree, cloud infrastructure, auth, billing or a generic AI layer.

## Development workflow

Run commands from the repository root. Typical local checks:

```powershell
python --version
robotci validate
ruff check .
pytest -vv
```

For frontend work, also run its TypeScript/build checks. For ROS/runtime changes, use the relevant native/Docker workflows when available.

Use Python 3.12, type annotations and small focused modules. Ruff is authoritative for lint/import order. Tests live under `tests/`; add regression coverage for behavior changes.

## Git and PR discipline

- Fetch before choosing a new task.
- Never force-push or rewrite shared history unless explicitly requested.
- Never reuse a branch whose PR was superseded when a clean branch from current `main` is safer.
- Keep commits meaningful; do not create activity for its own sake.
- Prefer one coherent concern per PR.
- Inspect the final diff before declaring success.
- Merge only after relevant CI and review provide sufficient confidence.
- After merge/closure, old merged or superseded branches are cleanup candidates; never delete active work or branches with unique unmerged changes.

## Multi-agent coordination

Issue #18 is the shared mailbox between local and cloud-side agents.

Use concise handoffs:

```text
[LOCAL -> CLOUD]
branch: ...
head: ...
task: ...
result: ...
conflict_risk: ...
needs_cloud: ...
```

or:

```text
[CLOUD -> LOCAL]
remote_state: ...
decision: ...
constraints: ...
recommended_task: ...
```

Do not post heartbeat/spam messages. Post when there is a meaningful result, blocker, architecture decision or ownership change.

## Local model routing

When Codex is launched with `--oss`, this repository defaults to Ollama via `.codex/config.toml`.

Use local inference for inexpensive work such as repository exploration, search, documentation, test generation, lint fixes, small refactors and CI-log triage. Escalate difficult architecture/debugging to a stronger cloud model when useful. Durable state belongs in Git, issue #18 and `.agent/STATE.md`, not only in a model context window.

## Safety boundaries

Agents may autonomously edit code, create branches/commits/PRs, run tests, fix CI, write docs and merge when checks are sufficient.

Ask Ivan before:

- deleting a repository;
- touching or deploying production;
- making a paid purchase or starting a paid service;
- performing a genuinely irreversible external action;
- publishing publicly as Ivan outside normal GitHub development workflows;
- changing secrets or credentials that affect external systems.

Never expose passwords, tokens, API keys or private credentials in source code, issues, logs or artifacts.
