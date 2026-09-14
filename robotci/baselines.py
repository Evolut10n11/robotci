from __future__ import annotations

import json
import re
import shutil
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from robotci.comparison import ComparisonInputError, load_scenario_result

BASELINE_SCHEMA_VERSION = 1
DEFAULT_BASELINE_ROOT = Path(".robotci") / "baselines"
_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class BaselineError(ValueError):
    """Raised when a baseline cannot be captured or loaded safely."""


@dataclass(frozen=True)
class BaselineInfo:
    name: str
    path: Path
    captured_at: str
    source_suite: str
    scenarios: tuple[str, ...]


def _load_json_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise BaselineError(f"{label} does not exist: {path}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise BaselineError(f"{label} is not valid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise BaselineError(f"{label} must contain a JSON object: {path}")
    return value


def _validate_name(name: str) -> None:
    if not _NAME_RE.fullmatch(name):
        raise BaselineError(
            "baseline name must be 1-64 characters using letters, numbers, '.', '_' or '-'"
        )


def _safe_result_path(suite_dir: Path, result_file: str) -> Path:
    relative = Path(result_file)
    if relative.is_absolute() or ".." in relative.parts:
        raise BaselineError(f"unsafe result_file path: {result_file}")

    suite_root = suite_dir.resolve()
    resolved = (suite_dir / relative).resolve()
    try:
        resolved.relative_to(suite_root)
    except ValueError as exc:
        raise BaselineError(f"result_file escapes suite directory: {result_file}") from exc
    return resolved


def _validated_suite(suite_path: Path) -> tuple[dict[str, Any], list[tuple[str, Path]]]:
    suite = _load_json_object(suite_path, label="suite result")
    if suite.get("status") != "PASS":
        raise BaselineError("only PASS suites can be captured as known-good baselines")

    scenarios = suite.get("scenarios")
    if not isinstance(scenarios, list) or not scenarios:
        raise BaselineError("suite result must contain a non-empty scenarios list")

    suite_dir = suite_path.parent
    seen: set[str] = set()
    validated: list[tuple[str, Path]] = []

    for item in scenarios:
        if not isinstance(item, dict):
            raise BaselineError("each suite scenario entry must be an object")
        scenario = item.get("scenario")
        result_file = item.get("result_file")
        status = item.get("status")
        if not isinstance(scenario, str) or not scenario:
            raise BaselineError("each suite scenario entry must have a scenario name")
        if scenario in seen:
            raise BaselineError(f"duplicate scenario in suite result: {scenario}")
        seen.add(scenario)
        if status != "PASS":
            raise BaselineError(f"scenario {scenario!r} is not PASS")
        if not isinstance(result_file, str) or not result_file:
            raise BaselineError(f"scenario {scenario!r} has no result_file")

        result_path = _safe_result_path(suite_dir, result_file)
        if not result_path.is_file():
            raise BaselineError(f"result for scenario {scenario!r} does not exist: {result_path}")
        try:
            result = load_scenario_result(result_path)
        except ComparisonInputError as exc:
            raise BaselineError(
                f"result for scenario {scenario!r} is not baseline-compatible: {exc}"
            ) from exc
        if result.scenario != scenario:
            raise BaselineError(
                f"scenario identity mismatch: suite has {scenario!r}, "
                f"result has {result.scenario!r}"
            )
        validated.append((result_file, result_path))

    return suite, validated


def capture_baseline(
    name: str,
    suite_path: Path | str,
    *,
    store_root: Path | str = DEFAULT_BASELINE_ROOT,
    replace: bool = False,
) -> BaselineInfo:
    """Capture a successful suite and all referenced results into a self-contained baseline."""

    _validate_name(name)
    source_suite = Path(suite_path).resolve()
    suite, result_files = _validated_suite(source_suite)

    root = Path(store_root)
    root.mkdir(parents=True, exist_ok=True)
    destination = root / name
    if destination.exists() and not replace:
        raise BaselineError(f"baseline already exists: {name}")

    captured_at = datetime.now(UTC).isoformat()
    manifest = {
        "schema_version": BASELINE_SCHEMA_VERSION,
        "name": name,
        "captured_at": captured_at,
        "source_suite": str(source_suite),
        "suite_file": "suite-result.json",
        "scenarios": [item["scenario"] for item in suite["scenarios"]],
    }

    with tempfile.TemporaryDirectory(prefix=f".{name}-", dir=root) as temp_dir:
        temp = Path(temp_dir)
        shutil.copy2(source_suite, temp / "suite-result.json")
        for relative_name, source in result_files:
            target = temp / relative_name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        (temp / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(temp, destination)

    return BaselineInfo(
        name=name,
        path=destination,
        captured_at=captured_at,
        source_suite=str(source_suite),
        scenarios=tuple(manifest["scenarios"]),
    )


def load_baseline_manifest(
    name: str, *, store_root: Path | str = DEFAULT_BASELINE_ROOT
) -> BaselineInfo:
    _validate_name(name)
    path = Path(store_root) / name
    manifest = _load_json_object(path / "manifest.json", label="baseline manifest")
    if manifest.get("schema_version") != BASELINE_SCHEMA_VERSION:
        raise BaselineError(
            f"unsupported baseline schema version: {manifest.get('schema_version')!r}"
        )
    if manifest.get("name") != name:
        raise BaselineError("baseline manifest name does not match directory name")

    scenarios = manifest.get("scenarios")
    if not isinstance(scenarios, list) or not all(isinstance(item, str) for item in scenarios):
        raise BaselineError("baseline manifest scenarios must be a list of names")
    captured_at = manifest.get("captured_at")
    source_suite = manifest.get("source_suite")
    if not isinstance(captured_at, str) or not isinstance(source_suite, str):
        raise BaselineError("baseline manifest is missing capture metadata")

    suite_file = manifest.get("suite_file")
    if suite_file != "suite-result.json" or not (path / suite_file).is_file():
        raise BaselineError("baseline suite file is missing or unsupported")

    return BaselineInfo(
        name=name,
        path=path,
        captured_at=captured_at,
        source_suite=source_suite,
        scenarios=tuple(scenarios),
    )


def list_baselines(*, store_root: Path | str = DEFAULT_BASELINE_ROOT) -> list[BaselineInfo]:
    root = Path(store_root)
    if not root.exists():
        return []
    entries: list[BaselineInfo] = []
    for child in sorted(root.iterdir(), key=lambda item: item.name):
        if child.is_dir() and _NAME_RE.fullmatch(child.name):
            entries.append(load_baseline_manifest(child.name, store_root=root))
    return entries


def baseline_suite_path(name: str, *, store_root: Path | str = DEFAULT_BASELINE_ROOT) -> Path:
    info = load_baseline_manifest(name, store_root=store_root)
    return info.path / "suite-result.json"


def remove_baseline(name: str, *, store_root: Path | str = DEFAULT_BASELINE_ROOT) -> None:
    _validate_name(name)
    destination = Path(store_root) / name
    if not destination.exists():
        raise BaselineError(f"baseline does not exist: {name}")
    if not destination.is_dir():
        raise BaselineError(f"baseline path is not a directory: {destination}")
    shutil.rmtree(destination)
