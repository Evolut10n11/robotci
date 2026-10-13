"""The exit marker must not precede the worker's fail-closed run state."""
from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from robotci.execution_worker import _record_exit

RUN_ID = "a" * 32


def _run_record(directory: Path, *, run_id: str = RUN_ID) -> bytes:
    payload = {
        "run_id": run_id,
        "state": "CANCELLING",
        "suite_status": "PASS",
        "suite_path": "artifacts/suite-result.json",
    }
    data = (json.dumps(payload) + "\n").encode()
    (directory / "run.json").write_bytes(data)
    return data


@pytest.mark.parametrize(
    "code,error,state",
    [(130, None, "CANCELLED"), (0, None, "FAILED"), (3, None, "FAILED"),
     (130, "cleanup failed", "FAILED")],
)
def test_exit_marker_waits_for_delayed_run_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    code: int, error: str | None, state: str,
) -> None:
    original = _run_record(tmp_path)
    ready, release = threading.Event(), threading.Event()
    publications: list[str] = []
    errors: list[BaseException] = []
    replace = Path.replace

    def delayed_replace(path: Path, target: Path) -> Path:
        if path.name == ".worker-run.json.tmp":
            ready.set()
            if not release.wait(timeout=5):
                raise TimeoutError("test did not release state publication")
        result = replace(path, target)
        publications.append(Path(target).name)
        return result

    def worker() -> None:
        try:
            _record_exit(tmp_path, RUN_ID, code, error)
        except BaseException as exc:
            errors.append(exc)

    monkeypatch.setattr(Path, "replace", delayed_replace)
    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    try:
        assert ready.wait(timeout=3), "worker never reached run-state publication"
        assert (tmp_path / "run.json").read_bytes() == original
        assert not (tmp_path / "worker.json").exists(), "exit marker was published too early"
    finally:
        release.set()
        thread.join(timeout=5)
    assert not thread.is_alive()
    assert errors == []
    assert publications == ["run.json", "worker.json"]
    metadata = json.loads((tmp_path / "run.json").read_text(encoding="utf-8"))
    marker = json.loads((tmp_path / "worker.json").read_text(encoding="utf-8"))
    assert metadata["state"] == state
    assert metadata["suite_status"] is None
    assert metadata["suite_path"] is None
    assert metadata["exit_code"] == marker["exit_code"] == code
    assert metadata["run_id"] == marker["run_id"] == RUN_ID
    assert metadata["finished_at"] == marker["finished_at"]
    assert marker["cleanup_error"] == error
    if code == 0:
        assert metadata["error"] == "awaiting owning server validation"


@pytest.mark.parametrize("operation", ["write", "replace"])
@pytest.mark.parametrize("stage", ["run", "marker"])
def test_failed_publication_never_leaves_an_exit_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, operation: str, stage: str,
) -> None:
    original = _run_record(tmp_path)
    target_name = ".worker-run.json.tmp" if stage == "run" else ".worker.json.tmp"
    method = "write_text" if operation == "write" else "replace"
    original_method = getattr(Path, method)

    def fail_at_stage(path: Path, *args, **kwargs):
        if path.name == target_name:
            raise OSError("injected publication failure")
        return original_method(path, *args, **kwargs)

    monkeypatch.setattr(Path, method, fail_at_stage)
    with pytest.raises(OSError, match="injected publication failure"):
        _record_exit(tmp_path, RUN_ID, 130, None)
    assert not (tmp_path / "worker.json").exists()
    if stage == "run":
        assert (tmp_path / "run.json").read_bytes() == original
    else:
        metadata = json.loads((tmp_path / "run.json").read_text(encoding="utf-8"))
        assert metadata["state"] == "CANCELLED"
        assert metadata["suite_status"] is None
        assert metadata["suite_path"] is None


@pytest.mark.parametrize("corruption", ["foreign_id", "broken_json", "missing"])
def test_invalid_run_metadata_cannot_publish_exit_marker(
    tmp_path: Path, corruption: str,
) -> None:
    _run_record(tmp_path, run_id="b" * 32)
    path = tmp_path / "run.json"
    if corruption == "broken_json":
        path.write_text("{broken", encoding="utf-8")
    elif corruption == "missing":
        path.unlink()
    original = path.read_bytes() if path.exists() else None
    with pytest.raises((ValueError, FileNotFoundError)):
        _record_exit(tmp_path, RUN_ID, 130, None)
    assert not (tmp_path / "worker.json").exists()
    assert (path.read_bytes() if path.exists() else None) == original
