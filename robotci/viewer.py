from __future__ import annotations

import json
import math
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

VIEWER_ASSETS_DIR = Path(__file__).with_name("viewer_assets")
DEFAULT_VIEWER_HOST = "127.0.0.1"
DEFAULT_VIEWER_PORT = 8765
MAX_REPLAY_BYTES = 32 * 1024 * 1024
MAX_REPLAY_SAMPLES = 250_000


class ViewerError(ValueError):
    """Raised when a replay cannot be loaded or served."""


def demo_replay() -> dict[str, Any]:
    """Return a deterministic Replay v1 artifact for viewer smoke-testing."""
    samples = [
        {"t": 0.0, "position": {"x": 0.0, "y": 0.0, "z": 0.0}, "orientation": {"yaw": 0.0}},
        {"t": 1.5, "position": {"x": 0.8, "y": 0.2, "z": 0.0}, "orientation": {"yaw": 0.18}},
        {"t": 3.0, "position": {"x": 1.7, "y": 0.6, "z": 0.0}, "orientation": {"yaw": 0.34}},
        {"t": 4.5, "position": {"x": 2.5, "y": 1.2, "z": 0.0}, "orientation": {"yaw": 0.52}},
        {"t": 6.0, "position": {"x": 2.7, "y": 1.35, "z": 0.0}, "orientation": {"yaw": 0.52}},
        {"t": 7.5, "position": {"x": 3.1, "y": 1.55, "z": 0.0}, "orientation": {"yaw": 0.42}},
        {"t": 9.0, "position": {"x": 3.9, "y": 2.05, "z": 0.0}, "orientation": {"yaw": 0.55}},
        {"t": 10.5, "position": {"x": 4.55, "y": 2.55, "z": 0.0}, "orientation": {"yaw": 0.64}},
        {"t": 12.0, "position": {"x": 5.0, "y": 3.0, "z": 0.0}, "orientation": {"yaw": 0.78}},
    ]
    return {
        "schema_version": 1,
        "scenario": "deterministic_demo",
        "status": "PASS",
        "runtime": "deterministic_demo",
        "duration_sec": 12.0,
        "robot": {"type": "generic_mobile_base"},
        "world": {
            "frame": "map",
            "goal": {"x": 5.0, "y": 3.0, "z": 0.0},
        },
        "samples": samples,
        "metrics": {
            "duration_sec": 12.0,
            "path_length_m": 6.05,
            "distance_to_goal_m": 0.0,
            "stuck_events": 1,
            "recoveries": 1,
        },
        "events": [
            {"t": 0.0, "type": "START", "message": "Navigation started"},
            {"t": 5.2, "type": "STUCK", "message": "Local planner stopped making progress"},
            {"t": 6.4, "type": "RECOVERY", "message": "Recovery behavior completed"},
            {"t": 12.0, "type": "GOAL", "message": "Goal reached"},
        ],
    }


def _require_mapping(value: object, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ViewerError(f"{name} must be an object")
    return value


def _require_number(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ViewerError(f"{name} must be a number")
    try:
        number = float(value)
    except OverflowError as exc:
        raise ViewerError(f"{name} must be finite") from exc
    if not math.isfinite(number):
        raise ViewerError(f"{name} must be finite")
    return number


def _validate_position(value: object, name: str) -> None:
    position = _require_mapping(value, name)
    for axis in ("x", "y", "z"):
        _require_number(position.get(axis), f"{name}.{axis}")


def validate_replay(payload: object) -> dict[str, Any]:
    """Validate the subset of Replay v1 required by the bundled viewer."""
    replay = dict(_require_mapping(payload, "replay"))

    if type(replay.get("schema_version")) is not int or replay["schema_version"] != 1:
        raise ViewerError("replay.schema_version must be 1")

    scenario = replay.get("scenario")
    if not isinstance(scenario, str) or not scenario.strip():
        raise ViewerError("replay.scenario must be a non-empty string")

    status = replay.get("status")
    if not isinstance(status, str) or status not in {"PASS", "FAIL"}:
        raise ViewerError("replay.status must be PASS or FAIL")
    result_status = replay.get("result_status", status)
    if not isinstance(result_status, str) or result_status not in {
        "PASS",
        "FAIL",
        "TIMEOUT",
        "INFRA_ERROR",
    }:
        raise ViewerError("replay.result_status is unsupported")
    if status != ("PASS" if result_status == "PASS" else "FAIL"):
        raise ViewerError("replay.status contradicts replay.result_status")

    runtime = replay.get("runtime")
    if not isinstance(runtime, str) or not runtime.strip():
        raise ViewerError("replay.runtime must be a non-empty string")

    duration = _require_number(replay.get("duration_sec"), "replay.duration_sec")
    if duration <= 0:
        raise ViewerError("replay.duration_sec must be greater than zero")

    robot = _require_mapping(replay.get("robot"), "replay.robot")
    robot_type = robot.get("type")
    if not isinstance(robot_type, str) or not robot_type.strip():
        raise ViewerError("replay.robot.type must be a non-empty string")

    world = _require_mapping(replay.get("world"), "replay.world")
    frame = world.get("frame")
    if not isinstance(frame, str) or not frame.strip():
        raise ViewerError("replay.world.frame must be a non-empty string")
    _validate_position(world.get("goal"), "replay.world.goal")

    samples = replay.get("samples")
    if not isinstance(samples, list) or len(samples) < 2:
        raise ViewerError("replay.samples must contain at least two samples")
    if len(samples) > MAX_REPLAY_SAMPLES:
        raise ViewerError(f"replay.samples exceeds {MAX_REPLAY_SAMPLES} samples")
    previous_t = -math.inf
    for index, raw_sample in enumerate(samples):
        sample = _require_mapping(raw_sample, f"replay.samples[{index}]")
        sample_t = _require_number(sample.get("t"), f"replay.samples[{index}].t")
        if sample_t < 0 or sample_t < previous_t:
            raise ViewerError("replay sample timestamps must be non-negative and ordered")
        if sample_t > duration:
            raise ViewerError("replay sample timestamp exceeds replay.duration_sec")
        previous_t = sample_t
        _validate_position(sample.get("position"), f"replay.samples[{index}].position")
        orientation = _require_mapping(
            sample.get("orientation"),
            f"replay.samples[{index}].orientation",
        )
        _require_number(
            orientation.get("yaw"),
            f"replay.samples[{index}].orientation.yaw",
        )

    metrics = _require_mapping(replay.get("metrics"), "replay.metrics")
    for key in (
        "duration_sec",
        "path_length_m",
        "distance_to_goal_m",
        "stuck_events",
        "recoveries",
    ):
        number = _require_number(metrics.get(key), f"replay.metrics.{key}")
        if number < 0:
            raise ViewerError(f"replay.metrics.{key} must be non-negative")
        if key in {"stuck_events", "recoveries"} and type(metrics[key]) is not int:
            raise ViewerError(f"replay.metrics.{key} must be an integer")
    if not math.isclose(metrics["duration_sec"], duration, rel_tol=1e-6, abs_tol=0.002):
        raise ViewerError("replay.metrics.duration_sec contradicts replay.duration_sec")

    events = replay.get("events")
    if not isinstance(events, list):
        raise ViewerError("replay.events must be an array")
    allowed_events = {"START", "REPLAN", "STUCK", "RECOVERY", "GOAL", "FAIL"}
    for index, raw_event in enumerate(events):
        event = _require_mapping(raw_event, f"replay.events[{index}]")
        event_t = _require_number(event.get("t"), f"replay.events[{index}].t")
        if event_t < 0 or event_t > duration:
            raise ViewerError(f"replay.events[{index}].t is outside the replay duration")
        event_type = event.get("type")
        if not isinstance(event_type, str) or event_type not in allowed_events:
            raise ViewerError(f"replay.events[{index}].type is unsupported")
        message = event.get("message")
        if message is not None and not isinstance(message, str):
            raise ViewerError(f"replay.events[{index}].message must be a string")

    return replay


def load_replay(path: Path) -> dict[str, Any]:
    """Load and validate a Replay v1 JSON artifact."""
    try:
        if path.stat().st_size > MAX_REPLAY_BYTES:
            raise ViewerError("replay file exceeds the 32 MiB size limit")
        payload = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_strict_object,
            parse_constant=_reject_constant,
            parse_float=lambda value: _require_number(float(value), "replay JSON number"),
        )
    except FileNotFoundError as exc:
        raise ViewerError(f"replay file does not exist: {path}") from exc
    except (OSError, UnicodeError) as exc:
        raise ViewerError(f"cannot read replay file: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ViewerError(f"replay file is not valid JSON: {exc.msg}") from exc
    return validate_replay(payload)


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ViewerError(f"duplicate replay JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ViewerError(f"invalid replay JSON number: {value}")


def _handler_for(
    replay: dict[str, Any] | None, session: dict[str, Any]
) -> type[SimpleHTTPRequestHandler]:
    encoded_replay = json.dumps(replay, separators=(",", ":"), allow_nan=False).encode("utf-8")
    encoded_session = json.dumps(session, separators=(",", ":"), allow_nan=False).encode("utf-8")

    class ReplayHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, directory=str(VIEWER_ASSETS_DIR), **kwargs)

        def _send_json(self, body: bytes, status: int = 200) -> None:
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
            path = urlsplit(self.path).path
            if path == "/api/replay":
                self._send_json(encoded_replay, status=200 if replay is not None else 404)
                return
            if path == "/api/session":
                self._send_json(encoded_session)
                return
            if path == "/healthz":
                self._send_json(b'{"status":"ok"}')
                return
            super().do_GET()

        def list_directory(self, path: str) -> None:
            self.send_error(404, "Not found")

        def log_message(self, format: str, *args: Any) -> None:
            return

    return ReplayHandler


def create_viewer_server(
    replay: dict[str, Any] | None,
    *,
    host: str = DEFAULT_VIEWER_HOST,
    port: int = DEFAULT_VIEWER_PORT,
    session: dict[str, Any] | None = None,
) -> ThreadingHTTPServer:
    """Create a local HTTP server for the bundled viewer."""
    if not VIEWER_ASSETS_DIR.joinpath("index.html").is_file():
        raise ViewerError(f"viewer assets are missing from {VIEWER_ASSETS_DIR}")
    if not 0 <= port <= 65535:
        raise ViewerError("viewer port must be between 0 and 65535")
    if session is None:
        from robotci.viewer_session import replay_session

        session = replay_session(validate_replay(replay))
    return ThreadingHTTPServer((host, port), _handler_for(replay, session))


def serve_viewer(
    replay: dict[str, Any] | None,
    *,
    host: str = DEFAULT_VIEWER_HOST,
    port: int = DEFAULT_VIEWER_PORT,
    open_browser: bool = True,
    session: dict[str, Any] | None = None,
) -> str:
    """Serve the viewer until interrupted and return its URL after shutdown."""
    server = create_viewer_server(replay, host=host, port=port, session=session)
    effective_host = host
    if effective_host in {"0.0.0.0", "::"}:
        effective_host = "127.0.0.1"
    effective_port = int(server.server_address[1])
    url = f"http://{effective_host}:{effective_port}/"

    if open_browser:
        webbrowser.open(url)

    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return url
