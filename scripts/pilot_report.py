"""Summarize human-recorded M8 evidence; never runs robots or contacts teams."""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import date
from pathlib import Path
from statistics import median
from typing import Any

SIGNALS = (
    "own_repo_suite",
    "baseline_saved",
    "real_candidate_gate",
    "reuse_intent",
    "paid_discussion",
)
TARGETS = {
    "teams_enrolled": 5,
    "own_repo_suite": 3,
    "real_candidate_gate": 2,
    "reuse_intent": 2,
    "paid_discussion": 1,
}
STATES = {"pending", "active", "completed", "blocked", "withdrawn"}


class EvidenceError(ValueError):
    """The registry is malformed or makes contradictory claims."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise EvidenceError(message)


def fields(value: Any, expected: set[str], path: str) -> None:
    require(isinstance(value, dict), f"{path}: expected an object")
    require(set(value) == expected, f"{path}: expected fields {', '.join(sorted(expected))}")


def nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def valid_minutes(value: Any) -> bool:
    if value is None:
        return True
    try:
        return type(value) in (int, float) and math.isfinite(value) and value >= 0
    except OverflowError:
        return False


def no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        require(key not in result, f"duplicate JSON key: {key}")
        result[key] = value
    return result


def reject_constant(value: str) -> None:
    raise EvidenceError(f"non-finite JSON number: {value}")


def load_registry(path: Path) -> dict[str, Any]:
    return json.loads(
        path.read_text(encoding="utf-8-sig"),
        object_pairs_hook=no_duplicates,
        parse_constant=reject_constant,
    )


def summarize(registry: Any) -> dict[str, Any]:
    fields(registry, {"schema_version", "pilots"}, "registry")
    require(
        type(registry["schema_version"]) is int and registry["schema_version"] == 1,
        "schema_version: only integer version 1 is supported",
    )
    pilots = registry["pilots"]
    require(isinstance(pilots, list) and len(pilots) == 5, "pilots: expected five cohort slots")
    ids: set[str] = set()
    teams: set[str] = set()
    counts = dict.fromkeys(TARGETS, 0)
    finished = 0
    setup_times: list[float] = []
    rows = []
    for index, pilot in enumerate(pilots):
        path = f"pilots[{index}]"
        fields(pilot, {"id", "team_id", "state", "setup_minutes", "blocker", "evidence"}, path)
        pilot_id = pilot["id"]
        require(
            isinstance(pilot_id, str) and pilot_id in {f"pilot-{n:02}" for n in range(1, 6)},
            f"{path}.id: expected pilot-01 through pilot-05",
        )
        require(pilot_id not in ids, f"{path}.id: duplicate pilot ID")
        ids.add(pilot_id)
        state = pilot["state"]
        require(isinstance(state, str) and state in STATES, f"{path}.state: unsupported state")
        team = pilot["team_id"]
        if state == "pending":
            require(team is None, f"{path}.team_id: pending slots are not enrolled teams")
        else:
            require(nonempty(team), f"{path}.team_id: enrolled team identifier required")
            team_key = team.strip().casefold()
            require(team_key not in teams, f"{path}.team_id: duplicate team")
            teams.add(team_key)
            counts["teams_enrolled"] += 1

        minutes = pilot["setup_minutes"]
        require(
            valid_minutes(minutes),
            f"{path}.setup_minutes: expected null or finite non-negative minutes",
        )
        blocker = pilot["blocker"]
        require(blocker is None or nonempty(blocker), f"{path}.blocker: expected null or text")
        if state in {"blocked", "withdrawn"}:
            require(nonempty(blocker), f"{path}.blocker: record the blocking or withdrawal reason")
        evidence = pilot["evidence"]
        fields(evidence, set(SIGNALS), f"{path}.evidence")
        outcomes: dict[str, bool | None] = {}
        for signal, observation in evidence.items():
            if observation is None:
                outcomes[signal] = None
                continue
            location = f"{path}.evidence.{signal}"
            fields(observation, {"observed_on", "outcome", "reference"}, location)
            require(type(observation["outcome"]) is bool, f"{location}.outcome: expected boolean")
            observed_on = observation["observed_on"]
            try:
                valid_date = isinstance(observed_on, str) and (
                    date.fromisoformat(observed_on).isoformat() == observed_on
                )
            except ValueError:
                valid_date = False
            require(valid_date, f"{location}.observed_on: expected YYYY-MM-DD")
            require(nonempty(observation["reference"]), f"{location}.reference: evidence required")
            outcomes[signal] = observation["outcome"]

        if state == "pending":
            require(
                all(value is None for value in outcomes.values())
                and minutes is None
                and blocker is None,
                f"{path}: pending slots cannot contain pilot observations",
            )
        if outcomes["baseline_saved"] is True:
            require(
                outcomes["own_repo_suite"] is True,
                f"{path}: baseline requires a successful suite on the team's repository",
            )
        if outcomes["real_candidate_gate"] is True:
            require(
                outcomes["baseline_saved"] is True,
                f"{path}: real candidate gate requires a saved baseline",
            )
        for signal in ("reuse_intent", "paid_discussion"):
            if outcomes[signal] is True:
                require(
                    outcomes["own_repo_suite"] is True,
                    f"{path}: {signal} counts only after real product use",
                )
        if state == "completed":
            require(
                all(value is not None for value in outcomes.values()),
                f"{path}: completed pilots need every outcome, including negative feedback",
            )
        if state in {"completed", "blocked", "withdrawn"}:
            finished += 1
        for signal in SIGNALS:
            if signal in counts and outcomes[signal] is True:
                counts[signal] += 1
        if outcomes["own_repo_suite"] is True and minutes is not None:
            setup_times.append(minutes)
        rows.append({"id": pilot_id, "state": state, "signals": outcomes})

    criteria = {
        name: {"actual": actual, "target": TARGETS[name], "met": actual >= TARGETS[name]}
        for name, actual in counts.items()
    }
    return {
        "schema_version": 1,
        "status": "READY_FOR_REVIEW" if finished == 5 else "AWAITING_EVIDENCE",
        "criteria_met": all(item["met"] for item in criteria.values()),
        "criteria": criteria,
        "pilots_finished": finished,
        "setup_minutes_median": median(setup_times) if setup_times else None,
        "setup_minutes_sample_size": len(setup_times),
        "pilots": sorted(rows, key=lambda row: row["id"]),
        "limitation": "Human-recorded evidence; references are not fetched or authenticated. "
        "A reviewed product decision is still required to close M8.",
    }


def markdown(report: dict[str, Any]) -> str:
    lines = [
        "# M8 validation evidence",
        "",
        f"Status: {report['status']}",
        "",
        f"Cohort success criteria met: {str(report['criteria_met']).lower()}",
        "",
        "| Criterion | Actual | Target | Met |",
        "| --- | ---: | ---: | --- |",
    ]
    for name, item in report["criteria"].items():
        lines.append(f"| {name} | {item['actual']} | {item['target']} | {item['met']} |")
    lines.extend(
        [
            "",
            f"Finished pilots: {report['pilots_finished']}/5",
            f"Median setup minutes: {report['setup_minutes_median']} "
            f"(n={report['setup_minutes_sample_size']})",
            "",
            "Signals below: yes / no / unknown. Unknown is not a negative result.",
            "",
            "| Pilot | State | Suite | Baseline | Candidate | Reuse | Paid discussion |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for pilot in report["pilots"]:
        signals = [
            "unknown" if pilot["signals"][s] is None else "yes" if pilot["signals"][s] else "no"
            for s in SIGNALS
        ]
        lines.append(f"| {pilot['id']} | {pilot['state']} | {' | '.join(signals)} |")
    return "\n".join([*lines, "", report["limitation"], ""])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("registry", type=Path)
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    args = parser.parse_args()
    try:
        report = summarize(load_registry(args.registry))
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"Invalid M8 registry: {exc}", file=sys.stderr)
        return 2
    print(
        json.dumps(report, indent=2, allow_nan=False)
        if args.format == "json"
        else markdown(report),
        end="\n" if args.format == "json" else "",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
