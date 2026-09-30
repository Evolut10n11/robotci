from __future__ import annotations

import copy
import json
import runpy
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "scripts" / "pilot_report.py"
MODULE = runpy.run_path(str(SCRIPT))
summarize = MODULE["summarize"]
EvidenceError = MODULE["EvidenceError"]


@pytest.fixture
def registry() -> dict:
    return {
        "schema_version": 1,
        "pilots": [
            {
                "id": f"pilot-{number:02}",
                "team_id": None,
                "state": "pending",
                "setup_minutes": None,
                "blocker": None,
                "evidence": {
                    signal: None
                    for signal in (
                        "own_repo_suite",
                        "baseline_saved",
                        "real_candidate_gate",
                        "reuse_intent",
                        "paid_discussion",
                    )
                },
            }
            for number in range(1, 6)
        ],
    }


def test_checked_in_registry_is_valid() -> None:
    # Real observations can evolve without changing the synthetic test cohort.
    summarize(MODULE["load_registry"](ROOT / "docs/validation/cohort.json"))


def observe(pilot: dict, signal: str, outcome: bool) -> None:
    pilot["evidence"][signal] = {
        "observed_on": "2026-09-21",
        "outcome": outcome,
        "reference": "Synthetic test observation, not external pilot evidence",
    }


def enroll(pilot: dict) -> None:
    pilot["state"] = "active"
    pilot["team_id"] = "test-" + pilot["id"]


def test_unobserved_cohort_is_not_validated(registry: dict) -> None:
    report = summarize(registry)
    assert report["status"] == "AWAITING_EVIDENCE"
    assert report["criteria_met"] is False
    assert all(metric["actual"] == 0 for metric in report["criteria"].values())
    assert report["setup_minutes_median"] is None
    assert report["pilots"][0]["signals"]["reuse_intent"] is None


def test_exact_thresholds_with_mixed_negative_outcomes(registry: dict) -> None:
    for index, pilot in enumerate(registry["pilots"]):
        enroll(pilot)
        for signal in pilot["evidence"]:
            observe(pilot, signal, False)
        if index < 3:
            observe(pilot, "own_repo_suite", True)
            pilot["setup_minutes"] = [0, 20, 40][index]
        if index < 2:
            for signal in ("baseline_saved", "real_candidate_gate", "reuse_intent"):
                observe(pilot, signal, True)
        if index == 0:
            observe(pilot, "paid_discussion", True)
        pilot["state"] = "completed"
    report = summarize(registry)
    assert report["status"] == "READY_FOR_REVIEW"
    assert report["criteria_met"] is True
    assert {k: v["actual"] for k, v in report["criteria"].items()} == {
        "teams_enrolled": 5,
        "own_repo_suite": 3,
        "real_candidate_gate": 2,
        "reuse_intent": 2,
        "paid_discussion": 1,
    }
    assert report["setup_minutes_median"] == 20
    assert report["setup_minutes_sample_size"] == 3
    # Interest in a feature does not replace an explicit paid discussion.
    observe(registry["pilots"][0], "paid_discussion", False)
    assert summarize(registry)["criteria_met"] is False


def test_finished_negative_cohort_can_be_reviewed_without_success(registry: dict) -> None:
    for pilot in registry["pilots"]:
        enroll(pilot)
        pilot["state"] = "blocked"
        pilot["blocker"] = "Runtime unavailable in synthetic test"
    report = summarize(registry)
    assert report["status"] == "READY_FOR_REVIEW"
    assert report["criteria_met"] is False


def test_missing_setup_time_is_excluded_from_median(registry: dict) -> None:
    for pilot in registry["pilots"][:2]:
        enroll(pilot)
        observe(pilot, "own_repo_suite", True)
    registry["pilots"][1]["setup_minutes"] = 30
    report = summarize(registry)
    assert report["setup_minutes_median"] == 30
    assert report["setup_minutes_sample_size"] == 1


@pytest.mark.parametrize(
    "signal", ["baseline_saved", "real_candidate_gate", "reuse_intent", "paid_discussion"]
)
def test_positive_claim_requires_real_use(registry: dict, signal: str) -> None:
    pilot = registry["pilots"][0]
    enroll(pilot)
    observe(pilot, signal, True)
    with pytest.raises(EvidenceError):
        summarize(registry)


@pytest.mark.parametrize("value", [True, -1, float("nan"), float("inf"), 10**400, "30"])
def test_invalid_setup_measurement(registry: dict, value: object) -> None:
    pilot = registry["pilots"][0]
    enroll(pilot)
    pilot["setup_minutes"] = value
    with pytest.raises(EvidenceError, match="setup_minutes"):
        summarize(registry)


@pytest.mark.parametrize(
    "mutation, message",
    [
        (lambda r: r.update(schema_version=True), "schema_version"),
        (lambda r: r["pilots"].pop(), "five cohort slots"),
        (lambda r: r["pilots"].append(copy.deepcopy(r["pilots"][0])), "five cohort slots"),
        (lambda r: r["pilots"][1].update(id="pilot-01"), "duplicate pilot ID"),
        (lambda r: r["pilots"][0].update(state=[]), "state"),
        (lambda r: r["pilots"][0].update(state="active"), "team_id"),
        (lambda r: r["pilots"][0].update(extra=True), "expected fields"),
    ],
)
def test_malformed_registry_is_rejected(registry: dict, mutation, message: str) -> None:
    mutation(registry)
    with pytest.raises(EvidenceError, match=message):
        summarize(registry)


def test_duplicate_team_cannot_inflate_counts(registry: dict) -> None:
    for pilot in registry["pilots"][:2]:
        enroll(pilot)
    registry["pilots"][1]["team_id"] = " TEST-PILOT-01 "
    with pytest.raises(EvidenceError, match="duplicate team"):
        summarize(registry)


@pytest.mark.parametrize(
    "change, message",
    [
        ({"outcome": "yes"}, "boolean"),
        ({"outcome": 1}, "boolean"),
        ({"observed_on": "2026-02-30"}, "YYYY-MM-DD"),
        ({"observed_on": 20260921}, "YYYY-MM-DD"),
        ({"reference": " "}, "evidence required"),
    ],
)
def test_claims_need_dated_evidence(registry: dict, change: dict, message: str) -> None:
    pilot = registry["pilots"][0]
    enroll(pilot)
    observe(pilot, "own_repo_suite", True)
    pilot["evidence"]["own_repo_suite"].update(change)
    with pytest.raises(EvidenceError, match=message):
        summarize(registry)


def test_pending_and_completed_states_cannot_hide_missing_evidence(registry: dict) -> None:
    pilot = registry["pilots"][0]
    observe(pilot, "own_repo_suite", True)
    with pytest.raises(EvidenceError, match="pending slots"):
        summarize(registry)
    enroll(pilot)
    pilot["state"] = "completed"
    with pytest.raises(EvidenceError, match="every outcome"):
        summarize(registry)
    pilot["state"] = "withdrawn"
    with pytest.raises(EvidenceError, match="withdrawal reason"):
        summarize(registry)


@pytest.mark.parametrize(
    "payload",
    [
        '{"schema_version":1,"schema_version":1,"pilots":[]}',
        '{"schema_version":1,"pilots":NaN}',
        '{"schema_version":1,"pilots":Infinity}',
        "{",
    ],
)
def test_cli_rejects_invalid_json_without_success_output(tmp_path: Path, payload: str) -> None:
    path = tmp_path / "cohort.json"
    path.write_text(payload, encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(path)], capture_output=True, text=True
    )
    assert result.returncode == 2
    assert result.stdout == ""
    assert "Invalid M8 registry" in result.stderr


def test_cli_runs_outside_checkout_with_utf8_bom(tmp_path: Path, registry: dict) -> None:
    path = tmp_path / "cohort.json"
    path.write_text(json.dumps(registry), encoding="utf-8-sig")
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(path), "--format", "json"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    report = json.loads(result.stdout)
    assert report["status"] == "AWAITING_EVIDENCE"
    assert "unknown" in MODULE["markdown"](report)
    assert "reviewed product decision" in MODULE["markdown"](report)
