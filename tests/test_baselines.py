import json
import shutil
from pathlib import Path

import pytest

from robotci.baselines import (
    BaselineError,
    baseline_suite_path,
    capture_baseline,
    list_baselines,
    load_baseline_manifest,
    remove_baseline,
)

FIXTURE = Path(__file__).parent / "fixtures" / "gate-suite" / "baseline"


def _copy_fixture(tmp_path: Path) -> Path:
    run = tmp_path / "run"
    shutil.copytree(FIXTURE, run)
    return run / "suite-result.json"


def test_capture_is_self_contained_after_source_is_removed(tmp_path: Path) -> None:
    suite = _copy_fixture(tmp_path)
    store = tmp_path / "baselines"

    info = capture_baseline("known-good", suite, store_root=store)
    shutil.rmtree(suite.parent)

    captured_suite = baseline_suite_path("known-good", store_root=store)
    payload = json.loads(captured_suite.read_text(encoding="utf-8"))
    result_file = info.path / payload["scenarios"][0]["result_file"]

    assert captured_suite.is_file()
    assert result_file.is_file()
    assert json.loads(result_file.read_text(encoding="utf-8"))["scenario"] == "route"


def test_capture_rejects_non_pass_suite(tmp_path: Path) -> None:
    suite = _copy_fixture(tmp_path)
    payload = json.loads(suite.read_text(encoding="utf-8"))
    payload["status"] = "FAIL"
    payload["scenarios"][0]["status"] = "FAIL"
    suite.write_text(json.dumps(payload), encoding="utf-8")
    result_path = suite.parent / "results/route.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    result.update(status="FAIL", navigation_result="ABORTED", reason_code="navigation_aborted")
    result_path.write_text(json.dumps(result), encoding="utf-8")

    with pytest.raises(BaselineError, match="only PASS suites"):
        capture_baseline("bad", suite, store_root=tmp_path / "baselines")


def test_capture_rejects_missing_referenced_result(tmp_path: Path) -> None:
    suite = _copy_fixture(tmp_path)
    (suite.parent / "results" / "route.json").unlink()

    with pytest.raises(BaselineError, match="does not exist"):
        capture_baseline("missing", suite, store_root=tmp_path / "baselines")


def test_capture_rejects_result_without_task_identity(tmp_path: Path) -> None:
    suite = _copy_fixture(tmp_path)
    result_path = suite.parent / "results" / "route.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    result.pop("task")
    result_path.write_text(json.dumps(result), encoding="utf-8")

    with pytest.raises(BaselineError, match="task must be an object"):
        capture_baseline("missing-task", suite, store_root=tmp_path / "baselines")


def test_capture_rejects_future_result_schema(tmp_path: Path) -> None:
    suite = _copy_fixture(tmp_path)
    result_path = suite.parent / "results" / "route.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    result["schema_version"] = 3
    result_path.write_text(json.dumps(result), encoding="utf-8")

    with pytest.raises(BaselineError, match="unsupported result.schema_version 3"):
        capture_baseline("future", suite, store_root=tmp_path / "baselines")


def test_capture_rejects_unsafe_result_path(tmp_path: Path) -> None:
    suite = _copy_fixture(tmp_path)
    payload = json.loads(suite.read_text(encoding="utf-8"))
    payload["scenarios"][0]["result_file"] = "../outside.json"
    suite.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(BaselineError, match="unsafe result_file"):
        capture_baseline("unsafe", suite, store_root=tmp_path / "baselines")


@pytest.mark.parametrize("name", ["../escape", "with space", "/absolute", ".hidden", ""])
def test_capture_rejects_unsafe_names(tmp_path: Path, name: str) -> None:
    suite = _copy_fixture(tmp_path)

    with pytest.raises(BaselineError, match="baseline name"):
        capture_baseline(name, suite, store_root=tmp_path / "baselines")


def test_capture_prevents_accidental_overwrite(tmp_path: Path) -> None:
    suite = _copy_fixture(tmp_path)
    store = tmp_path / "baselines"
    capture_baseline("stable", suite, store_root=store)

    with pytest.raises(BaselineError, match="already exists"):
        capture_baseline("stable", suite, store_root=store)


def test_explicit_replace_updates_capture(tmp_path: Path) -> None:
    suite = _copy_fixture(tmp_path)
    store = tmp_path / "baselines"
    capture_baseline("stable", suite, store_root=store)

    result_path = suite.parent / "results" / "route.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    result["metrics"]["path_length_m"] = 4.5
    result_path.write_text(json.dumps(result), encoding="utf-8")
    capture_baseline("stable", suite, store_root=store, replace=True)

    captured_result = store / "stable" / "results" / "route.json"
    captured = json.loads(captured_result.read_text(encoding="utf-8"))
    assert captured["metrics"]["path_length_m"] == 4.5


def test_list_show_and_remove_baselines(tmp_path: Path) -> None:
    suite = _copy_fixture(tmp_path)
    store = tmp_path / "baselines"
    capture_baseline("beta", suite, store_root=store)
    capture_baseline("alpha", suite, store_root=store)

    entries = list_baselines(store_root=store)
    shown = load_baseline_manifest("alpha", store_root=store)

    assert [entry.name for entry in entries] == ["alpha", "beta"]
    assert shown.scenarios == ("route",)
    assert shown.captured_at
    assert shown.source_suite.endswith("suite-result.json")

    remove_baseline("alpha", store_root=store)
    assert [entry.name for entry in list_baselines(store_root=store)] == ["beta"]


def test_load_rejects_corrupt_manifest(tmp_path: Path) -> None:
    store = tmp_path / "baselines"
    target = store / "broken"
    target.mkdir(parents=True)
    (target / "manifest.json").write_text("not-json", encoding="utf-8")

    with pytest.raises(BaselineError, match="not valid JSON"):
        load_baseline_manifest("broken", store_root=store)


def test_capture_rejects_suite_without_reproducibility_contract(tmp_path: Path) -> None:
    suite = _copy_fixture(tmp_path)
    payload = json.loads(suite.read_text(encoding="utf-8"))
    payload.pop("schema_version")
    payload.pop("execution")
    suite.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(BaselineError, match="schema_version must be 1"):
        capture_baseline("legacy", suite, store_root=tmp_path / "baselines")


def test_capture_rejects_tampered_environment_fingerprint(tmp_path: Path) -> None:
    suite = _copy_fixture(tmp_path)
    payload = json.loads(suite.read_text(encoding="utf-8"))
    payload["execution"]["environment"]["python_version"] = "3.12.99"
    suite.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(BaselineError, match="fingerprint does not match its contents"):
        capture_baseline("tampered", suite, store_root=tmp_path / "baselines")


def test_inconsistent_source_cannot_replace_existing_baseline(tmp_path: Path) -> None:
    suite = _copy_fixture(tmp_path)
    store = tmp_path / "baselines"
    captured = capture_baseline("known-good", suite, store_root=store)
    original = {
        path.relative_to(captured.path): path.read_bytes()
        for path in captured.path.rglob("*") if path.is_file()
    }
    payload = json.loads(suite.read_text(encoding="utf-8"))
    payload["scenarios"][0]["duration_sec"] = 999.0
    suite.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(BaselineError, match="duration"):
        capture_baseline("known-good", suite, store_root=store, replace=True)
    with pytest.raises(BaselineError, match="duration"):
        capture_baseline("invalid-new", suite, store_root=store)

    assert not (store / "invalid-new").exists()
    assert {
        path.relative_to(captured.path): path.read_bytes()
        for path in captured.path.rglob("*") if path.is_file()
    } == original


@pytest.mark.parametrize("version", [0, 1])
def test_readable_legacy_result_cannot_be_captured_as_known_good(
    tmp_path: Path, version: int,
) -> None:
    suite = _copy_fixture(tmp_path)
    result_path = suite.parent / "results/route.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    result["schema_version"] = version
    result.pop("telemetry_quality")
    result.pop("evidence_policy")
    if version == 0:
        result.pop("task")
    result_path.write_text(json.dumps(result), encoding="utf-8")

    with pytest.raises(BaselineError, match="not baseline-compatible"):
        capture_baseline("legacy", suite, store_root=tmp_path / "baselines")


def test_inconsistent_copied_result_cannot_replace_existing_baseline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    suite = _copy_fixture(tmp_path)
    store = tmp_path / "baselines"
    captured = capture_baseline("known-good", suite, store_root=store)
    original = {
        path.relative_to(captured.path): path.read_bytes()
        for path in captured.path.rglob("*") if path.is_file()
    }
    copy2 = shutil.copy2

    def copy_changed_result(source: Path, target: Path) -> str | Path:
        copied = copy2(source, target)
        if Path(target).name == "route.json":
            payload = json.loads(Path(target).read_text(encoding="utf-8"))
            payload["duration_sec"] += 1
            Path(target).write_text(json.dumps(payload), encoding="utf-8")
        return copied

    monkeypatch.setattr("robotci.baselines.shutil.copy2", copy_changed_result)

    with pytest.raises(BaselineError, match="duration"):
        capture_baseline("known-good", suite, store_root=store, replace=True)

    assert {
        path.relative_to(captured.path): path.read_bytes()
        for path in captured.path.rglob("*") if path.is_file()
    } == original
