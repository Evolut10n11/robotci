from __future__ import annotations

import json
import shutil
import threading
from pathlib import Path
from urllib.request import urlopen

import pytest

from robotci.baselines import BaselineError, capture_baseline
from robotci.regression import RegressionPolicy
from robotci.viewer import (
    ViewerError,
    create_viewer_server,
    demo_replay,
    load_replay,
    validate_replay,
)
from robotci.viewer_session import demo_session, replay_session, suite_session

FIXTURES = Path(__file__).parent / "fixtures" / "gate-suite"


def copy_suite(tmp_path: Path, name: str) -> Path:
    target = tmp_path / name
    shutil.copytree(FIXTURES / name, target)
    return target / "suite-result.json"


def add_sidecar(suite: Path) -> Path:
    result = json.loads((suite.parent / "results" / "route.json").read_text())
    replay = demo_replay()
    replay.update(scenario=result["scenario"], duration_sec=result["duration_sec"])
    replay["metrics"] = {**result["metrics"], "duration_sec": result["duration_sec"]}
    replay["world"]["goal"] = {**{k: result["goal"][k] for k in ("x", "y")}, "z": 0}
    replay["samples"] = [
        {"t": t, "position": {"x": p["x"], "y": p["y"], "z": 0}, "orientation": {"yaw": p["yaw"]}}
        for t, p in [(0, result["start"]), (result["duration_sec"], result["goal"])]
    ]
    replay["events"] = []
    target = suite.parent / "results" / "route.replay.json"
    target.write_text(json.dumps(replay))
    return target


def test_demo_is_explicitly_synthetic_and_has_no_official_gate() -> None:
    session = demo_session()
    assert session["source"] == "demo"
    assert session["gate"] is None
    entry = session["scenarios"][0]
    assert (
        entry["baseline"]["metrics"]["duration_sec"] < entry["candidate"]["metrics"]["duration_sec"]
    )
    assert entry["alignment_notice"] is None
    validate_replay(entry["baseline"]["replay"])


def test_visual_comparison_cannot_create_a_gate_verdict() -> None:
    candidate, baseline = demo_replay(), demo_replay()
    candidate["metrics"]["recoveries"] = 100
    session = replay_session(candidate, baseline)
    assert session["gate"] is None
    assert session["scenarios"][0]["comparison"] is None
    baseline["world"]["frame"] = "odom"
    assert (
        "coordinate frames"
        in replay_session(candidate, baseline)["scenarios"][0]["alignment_notice"]
    )


def test_suite_comparison_reuses_the_verified_gate_and_keeps_missing_replays_explicit(
    tmp_path: Path,
) -> None:
    baseline, candidate = copy_suite(tmp_path, "baseline"), copy_suite(tmp_path, "regression")
    session = suite_session(candidate, baseline)
    assert session["gate"]["status"] == "REGRESSION"
    entry = session["scenarios"][0]
    assert entry["comparison"]["status"] == "REGRESSION"
    assert {f["metric"] for f in entry["comparison"]["findings"]} == {
        "duration_sec",
        "path_length_m",
        "distance_to_goal_m",
        "stuck_events",
        "recoveries",
    }
    assert entry["candidate"]["replay"] is None
    assert "No trajectory" in entry["candidate"]["replay_notice"]
    assert str(tmp_path) not in json.dumps(session)


def test_suite_comparison_respects_explicit_policy(tmp_path: Path) -> None:
    baseline, candidate = copy_suite(tmp_path, "baseline"), copy_suite(tmp_path, "regression")
    session = suite_session(candidate, baseline, policy=RegressionPolicy(100, 100, 1, 10, 10))
    assert session["gate"]["status"] == "PASS"
    assert session["gate"]["policy"]["max_duration_increase_pct"] == 100


def test_mismatched_task_never_gets_a_gate_verdict(tmp_path: Path) -> None:
    baseline, candidate = copy_suite(tmp_path, "baseline"), copy_suite(tmp_path, "regression")
    result_path = candidate.parent / "results" / "route.json"
    result = json.loads(result_path.read_text())
    from dataclasses import asdict

    from robotci.results import Pose2D, build_scenario_task

    result["task"] = asdict(
        build_scenario_task(
            scenario="route",
            start=Pose2D(**result["start"]),
            goal=Pose2D(**result["goal"]),
            map_id="another-map",
        )
    )
    result_path.write_text(json.dumps(result))
    session = suite_session(candidate, baseline)
    assert session["gate"] is None
    assert "different tasks" in session["gate_notice"]


def test_stale_replay_is_not_shown_as_the_trajectory_for_another_result(tmp_path: Path) -> None:
    suite = copy_suite(tmp_path, "baseline")
    sidecar = add_sidecar(suite)
    assert suite_session(suite)["scenarios"][0]["candidate"]["replay"] is not None
    replay = json.loads(sidecar.read_text())
    replay["metrics"]["path_length_m"] += 1
    sidecar.write_text(json.dumps(replay))
    candidate = suite_session(suite)["scenarios"][0]["candidate"]
    assert candidate["replay"] is None
    assert "does not match" in candidate["replay_notice"]


def test_baseline_preserves_valid_replays_after_original_run_is_removed(tmp_path: Path) -> None:
    suite = copy_suite(tmp_path, "baseline")
    sidecar = add_sidecar(suite)
    original = sidecar.read_bytes()
    captured = capture_baseline("known-good", suite, store_root=tmp_path / "saved")
    shutil.rmtree(suite.parent)
    assert (captured.path / "results" / sidecar.name).read_bytes() == original
    assert suite_session(captured.path / "suite-result.json")["scenarios"][0]["candidate"]["replay"]


def test_invalid_optional_replay_does_not_replace_existing_baseline(tmp_path: Path) -> None:
    suite = copy_suite(tmp_path, "baseline")
    sidecar = add_sidecar(suite)
    captured = capture_baseline("known-good", suite, store_root=tmp_path / "saved")
    original = (captured.path / "results" / sidecar.name).read_bytes()
    sidecar.write_text("{}")
    with pytest.raises(BaselineError, match="cannot capture replay"):
        capture_baseline("known-good", suite, store_root=tmp_path / "saved", replace=True)
    assert (captured.path / "results" / sidecar.name).read_bytes() == original


def test_suite_session_is_served_without_exposing_filesystem_paths(tmp_path: Path) -> None:
    session = suite_session(copy_suite(tmp_path, "baseline"))
    server = create_viewer_server(None, session=session, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with urlopen(f"http://127.0.0.1:{server.server_port}/api/session", timeout=2) as response:
            assert json.loads(response.read()) == session
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.mark.parametrize(
    "field,value", [("status", {}), ("result_status", []), ("schema_version", True)]
)
def test_replay_rejects_invalid_enum_and_version_types(field: str, value: object) -> None:
    replay = demo_replay()
    replay[field] = value
    with pytest.raises(ViewerError):
        validate_replay(replay)


@pytest.mark.parametrize(
    "payload", ['{"schema_version":1,"schema_version":1}', '{"x":NaN}', '{"x":1e999}']
)
def test_replay_rejects_ambiguous_or_non_finite_json(tmp_path: Path, payload: str) -> None:
    path = tmp_path / "replay.json"
    path.write_text(payload)
    with pytest.raises(ViewerError):
        load_replay(path)


def test_failed_suite_is_inspectable_but_cannot_claim_a_regression_gate(tmp_path: Path) -> None:
    baseline, candidate = copy_suite(tmp_path, "baseline"), copy_suite(tmp_path, "regression")
    result_path = candidate.parent / "results" / "route.json"
    result = json.loads(result_path.read_text())
    result["status"] = "FAIL"
    result["navigation_result"] = "ABORTED"
    result["reason_code"] = "navigation_aborted"
    result_path.write_text(json.dumps(result))
    suite = json.loads(candidate.read_text())
    suite["status"] = "FAIL"
    suite["scenarios"][0]["status"] = "FAIL"
    candidate.write_text(json.dumps(suite))
    session = suite_session(candidate, baseline)
    assert session["gate"] is None
    assert session["gate_notice"].startswith("Gate unavailable:")
    assert session["scenarios"][0]["candidate"]["status"] == "FAIL"
