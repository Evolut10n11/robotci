"""Exercise installed RobotCI consumers against a recorded suite, without simulation.

All mutations are explicit synthetic controls in a temporary directory. Originals
and the user's baseline store are never written. This is not external pilot evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.request import ProxyHandler, build_opener

from robotci import __version__
from robotci.mcp.serializers import serialize_scenario_result, serialize_suite_comparison
from robotci.replay import default_replay_path
from robotci.suite_comparison import compare_suite_result_files
from robotci.suite_schema import load_suite_result
from robotci.viewer import VIEWER_ASSETS_DIR, create_viewer_server, load_replay
from robotci.viewer_session import demo_session, replay_matches_result, suite_session


class AcceptanceError(ValueError):
    """A consumer violated the post-run acceptance contract."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AcceptanceError(message)


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _cli(arguments: list[str], *, cwd: Path, expected: int) -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "robotci.baseline_cli", *arguments],
        cwd=cwd,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    _require(
        completed.returncode == expected,
        f"baseline CLI {arguments[0]}: expected exit {expected}, got {completed.returncode}\n"
        f"{completed.stdout}\n{completed.stderr}",
    )


def _gate(candidate: Path, *, store: Path, root: Path, label: str, expected: int,
          count: int) -> dict[str, object] | None:
    reports = [root / f"{label}.{extension}" for extension in ("json", "md", "xml")]
    _cli(
        ["gate", "acceptance", "--store", str(store), "--candidate", str(candidate),
         "--output", str(reports[0]), "--markdown-output", str(reports[1]),
         "--junit-output", str(reports[2])],
        cwd=root, expected=expected,
    )
    if expected == 3:
        _require(not any(path.exists() for path in reports), "invalid input produced a report")
        return None
    payload = json.loads(reports[0].read_text(encoding="utf-8"))
    status = "PASS" if expected == 0 else "REGRESSION"
    _require(payload["status"] == status, "JSON verdict differs from exit code")
    _require(len(payload["scenarios"]) == count, "JSON scenario count differs")
    _require(status in reports[1].read_text(encoding="utf-8"), "Markdown verdict differs")
    junit = ET.parse(reports[2]).getroot()
    _require(junit.attrib["tests"] == str(count), "JUnit scenario count differs")
    _require(junit.attrib["failures"] == ("0" if expected == 0 else "1"),
             "JUnit failures differ")
    return payload


def _http_check(session: dict[str, object]) -> None:
    server = create_viewer_server(None, host="127.0.0.1", port=0, session=session)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    opener = build_opener(ProxyHandler({}))  # A loopback-only request must not use a proxy.
    origin = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        for endpoint in ("/healthz", "/api/session", "/"):
            with opener.open(origin + endpoint, timeout=5) as response:
                content = response.read()
                _require(response.status == 200, "viewer endpoint did not respond")
                if endpoint == "/api/session":
                    _require(json.loads(content) == session, "viewer changed session evidence")
                elif endpoint == "/healthz":
                    _require(json.loads(content)["status"] == "ok", "viewer health failed")
                else:
                    _require(b"<html" in content.lower(), "viewer index missing")
        assets = sorted((VIEWER_ASSETS_DIR / "assets").glob("*"))
        _require(any(p.suffix == ".js" for p in assets), "viewer JavaScript missing")
        _require(any(p.suffix == ".css" for p in assets), "viewer stylesheet missing")
        for path in assets:
            if path.is_file():
                with opener.open(origin + "/assets/" + path.name, timeout=5) as response:
                    _require(response.read() == path.read_bytes(), "viewer asset bytes differ")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    _require(not thread.is_alive(), "viewer server did not stop")


def verify(suite_path: Path) -> dict[str, object]:
    suite_path = suite_path.resolve()
    suite = load_suite_result(suite_path)
    _require(suite.status == "PASS", "acceptance needs a successful recorded suite")
    files = {suite_path: "suite-result.json"}
    for item in suite.scenarios:
        files[item.result_path] = item.result_file
        replay_path = default_replay_path(item.result_path)
        _require(replay_path.resolve().is_relative_to(suite_path.parent),
                 "replay must remain inside the suite directory")
        replay = load_replay(replay_path)
        replay_matches_result(replay, item.result)
        files[replay_path] = str(Path(item.result_file).with_name(replay_path.name))
        serialized = serialize_scenario_result(item.result)
        _require(serialized["status"] == item.status, "MCP scenario status differs")
        _require(serialized["duration_sec"] == item.duration_sec, "MCP duration differs")
    original_hashes = {path: _digest(path) for path in files}
    checks = ["suite_and_replay_consistency", "mcp_scenario_serialization"]
    count = len(suite.scenarios)

    with tempfile.TemporaryDirectory(prefix="robotci-postrun-") as directory:
        root = Path(directory)
        working = root / "working"
        for source, relative in files.items():
            destination = working / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
        candidate = working / "suite-result.json"
        store = root / "baselines"
        save = ["save", "acceptance", "--suite", str(candidate), "--store", str(store)]
        _cli(save, cwd=root, expected=0)
        baseline = store / "acceptance" / "suite-result.json"
        baseline_hashes = {p: _digest(p) for p in store.rglob("*") if p.is_file()}
        _cli(save, cwd=root, expected=3)
        _require(all(_digest(p) == h for p, h in baseline_hashes.items()),
                 "duplicate save modified the baseline")
        checks.extend(["baseline_capture", "baseline_overwrite_refused"])
        _gate(candidate, store=store, root=root, label="unchanged", expected=0, count=count)
        checks.append("self_comparison_pass_and_three_report_formats")
        session = suite_session(candidate, baseline)
        _require(session["gate"]["status"] == "PASS", "viewer gate differs")
        _require(all(s["candidate"]["replay"] and s["baseline"]["replay"]
                     for s in session["scenarios"]), "viewer dropped a valid replay")
        _http_check(session)
        checks.append("viewer_session_and_http_assets")
        comparison = compare_suite_result_files(baseline_path=baseline, candidate_path=candidate)
        _require(serialize_suite_comparison(comparison)["status"] == "PASS",
                 "MCP comparison status differs")
        checks.append("mcp_comparison_serialization")

        # This is deliberately NOT a measured intervention. Keep original bytes intact.
        control_root = root / "synthetic-duration-control"
        shutil.copytree(working, control_root)
        control = control_root / "suite-result.json"
        payload = json.loads(control.read_text(encoding="utf-8"))
        first = payload["scenarios"][0]
        result_path = control_root / first["result_file"]
        result = json.loads(result_path.read_text(encoding="utf-8"))
        duration = float(result["duration_sec"]) * 2 + 1
        result["duration_sec"] = first["duration_sec"] = duration
        result_path.write_text(json.dumps(result, allow_nan=False), encoding="utf-8")
        control.write_text(json.dumps(payload, allow_nan=False), encoding="utf-8")
        regression = _gate(control, store=store, root=root, label="synthetic-regression",
                           expected=4, count=count)
        findings = [f["metric"] for s in regression["scenarios"] for f in s["findings"]]
        _require(findings == ["duration_sec"], "synthetic control did not isolate duration")
        stale_session = suite_session(control, baseline)
        changed = next(s for s in stale_session["scenarios"] if s["name"] == first["scenario"])
        _require(changed["candidate"]["replay"] is None, "stale replay was displayed")
        _require(bool(changed["candidate"]["replay_notice"]), "stale replay has no notice")
        checks.extend(["synthetic_regression_exit_4_and_three_report_formats",
                       "stale_replay_hidden"])

        broken_root = root / "synthetic-invalid-control"
        shutil.copytree(working, broken_root)
        broken = broken_root / "suite-result.json"
        payload = json.loads(broken.read_text(encoding="utf-8"))
        payload["scenarios"][0]["duration_sec"] += 1
        broken.write_text(json.dumps(payload), encoding="utf-8")
        _gate(broken, store=store, root=root, label="inconsistent", expected=3, count=count)
        checks.append("inconsistent_summary_exit_3_without_report")
        shutil.copyfile(candidate, broken)
        (broken_root / payload["scenarios"][0]["result_file"]).unlink()
        _gate(broken, store=store, root=root, label="missing", expected=3, count=count)
        checks.append("missing_result_exit_3_without_report")
        demo = demo_session()
        _require(demo["source"] == "demo" and demo["gate"] is None,
                 "synthetic demo advertised an official gate")
        checks.append("demo_has_no_official_gate")
        shutil.rmtree(working)
        _cli(["show", "acceptance", "--store", str(store)], cwd=root, expected=0)
        _gate(baseline, store=store, root=root, label="retained", expected=0, count=count)
        _require(all(_digest(p) == h for p, h in baseline_hashes.items()),
                 "consumer checks modified the captured baseline")
        checks.append("baseline_survives_source_removal")

    _require(all(_digest(path) == digest for path, digest in original_hashes.items()),
             "source evidence changed during acceptance")
    checks.append("original_evidence_unchanged")
    return {
        "schema_version": 1, "status": "PASS", "robotci_version": __version__,
        "runtime": suite.runtime, "scenario_count": count,
        "source_suite_sha256": original_hashes[suite_path],
        "execution_fingerprint": suite.execution.fingerprint,
        "checks": checks,
        "scope": "postrun_consumer_acceptance",
        "synthetic_controls": True,
        "new_simulation_executed": False,
        "external_pilot_evidence": False,
        "browser_rendering_checked": False,
        "mcp_transport_checked": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", required=True, type=Path,
                        help="Existing successful suite with result and replay files.")
    args = parser.parse_args(argv)
    try:
        report = verify(args.suite)
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print(f"Post-run acceptance failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
