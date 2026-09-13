# Contributing to RobotCI

RobotCI is developed through small, reviewable pull requests against `main`. Keep the repository easy to understand for humans and coding agents: one task per branch, one clear PR, and delete the branch after the work lands.

## Before you start

1. Sync the repository and prune deleted remote refs:

   ```bash
   git fetch --prune
   git switch main
   git pull --ff-only
   ```

2. Read `README.md` and `AGENTS.md`.
3. Check open pull requests and issue #18 (`Agent Coordination`) before starting work that could overlap another contributor or agent.
4. Do not start a second implementation of work already owned by an active branch or PR.

## Branches

Create a short-lived branch from current `main`.

Use these prefixes:

- `feat/` — product capability
- `fix/` — bug or runtime fix
- `docs/` — documentation only
- `ci/` — CI/workflow changes
- `test/` — test-only changes
- `chore/` — maintenance/tooling

Examples:

```text
feat/mujoco-adapter
fix/nav2-startup-race
docs/contributor-workflow
ci/replay-artifacts
```

Avoid generic names such as `test`, `new`, `work`, or `v2`. If a PR must be replaced, close the old PR explicitly and create one clean replacement branch with a descriptive name; do not leave parallel stale branches behind.

## Scope and ownership

Keep each branch focused. A PR should have one primary reason to exist.

If another contributor or agent owns a feature, do not edit its files just to make unrelated progress. Prefer an independent slice or coordinate ownership through issue #18 first.

Never force-push or rewrite a shared branch unless every active owner has explicitly agreed.

## Local checks

For cross-platform core changes, run:

```bash
robotci validate
ruff check .
pytest -vv
```

For frontend/replay changes, also run the frontend type/build checks documented by that package.

ROS2/Nav2 behavior is validated by the GitHub workflows on Ubuntu. Do not weaken or bypass a deterministic robot-behavior failure just to make CI green.

## Pull requests

A PR should explain:

- what changed;
- why the change is needed;
- what was intentionally not changed;
- how it was tested;
- whether it overlaps another active branch/PR.

Prefer a small vertical slice over a large speculative refactor. Keep deterministic RobotCI verdicts separate from future LLM explanations.

Do not merge while required checks are failing or while an unresolved review comment identifies a correctness issue.

## After merge

Once work is safely in `main`:

1. delete the remote feature branch;
2. prune local remote-tracking refs with `git fetch --prune`;
3. delete the local branch when it is no longer needed;
4. close or update superseded issues/PRs so the repository reflects the current state.

The normal steady state should be:

```text
main
+ only branches for work that is actively in progress
```

Merged, superseded, abandoned, and empty branches should not accumulate.

## Agent coordination

Issue #18 is the shared mailbox for local and cloud coding agents. Use concise handoffs after meaningful work or an ownership change; do not post heartbeat noise.

Before an agent starts significant work it should inspect current Git state, open PRs, `README.md`, `AGENTS.md`, and the latest coordination handoff.

Human instructions always override agent ownership conventions.