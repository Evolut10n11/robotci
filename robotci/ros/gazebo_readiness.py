"""Bounded ROS/Gazebo readiness and independent start-pose evidence.

ROS imports are deliberately deferred so the cross-platform core can test the
evidence helpers without installing a simulator. This module never moves the
physical robot; the adapter creates it in a fresh Gazebo partition first.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import subprocess
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import yaml

from robotci.metrics import planar_yaw_from_quaternion

START_TOLERANCE_M = 0.15
START_YAW_TOLERANCE_RAD = 0.15
MAP_CLEARANCE_M = 0.55
REQUIRED_LIFECYCLE_NODES = (
    "map_server",
    "amcl",
    "planner_server",
    "controller_server",
    "bt_navigator",
    "behavior_server",
    "velocity_smoother",
    "collision_monitor",
)
CONTROLLER_PARAMETER_NAMES = (
    "FollowPath.plugin", "FollowPath.vx_max", "FollowPath.visualize",
    "FollowPath.regenerate_noises", "general_goal_checker.xy_goal_tolerance",
    "general_goal_checker.yaw_goal_tolerance", "general_goal_checker.stateful",
    "FollowPath.GoalAngleCritic.threshold_to_consider",
)
BEHAVIOR_TREE_PARAMETER = "default_nav_to_pose_bt_xml"


def validate_benchmark_preset(preset: dict[str, Any]) -> None:
    for name in ("visualize", "regenerate_noises", "stateful"):
        if not isinstance(preset.get(name), bool):
            raise ValueError(f"benchmark {name} must be a boolean")
    for name in ("xy_goal_tolerance", "yaw_goal_tolerance", "goal_angle_activation_distance"):
        value = preset.get(name)
        try:
            valid = (not isinstance(value, bool) and isinstance(value, int | float)
                     and math.isfinite(value) and value > 0)
        except OverflowError:
            valid = False
        if not valid:
            raise ValueError(f"benchmark {name} must be a finite positive number")


def decode_controller_parameters(values: list[Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Validate ROS ParameterValue types before recording effective settings."""
    if len(values) != len(CONTROLLER_PARAMETER_NAMES):
        raise ValueError("controller read-back is incomplete")
    for name, value, expected_type in zip(
        CONTROLLER_PARAMETER_NAMES, values, (4, 3, 1, 1, 3, 3, 1, 3), strict=True
    ):
        if value.type != expected_type:
            raise ValueError(f"controller {name} has the wrong ROS parameter type")
    plugin, speed, visualize, noises, xy, yaw, stateful, angle_distance = values
    controller = {"plugin": plugin.string_value, "vx_max": speed.double_value}
    if (not math.isfinite(speed.double_value) or speed.double_value <= 0
            or isinstance(speed.double_value, bool)):
        raise ValueError("effective FollowPath.vx_max must be finite and positive")
    preset = {
        "visualize": visualize.bool_value, "regenerate_noises": noises.bool_value,
        "xy_goal_tolerance": xy.double_value, "yaw_goal_tolerance": yaw.double_value,
        "stateful": stateful.bool_value,
        "goal_angle_activation_distance": angle_distance.double_value,
    }
    validate_benchmark_preset(preset)
    return controller, preset


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return f"sha256:{digest.hexdigest()}"


def behavior_tree_record(value: Any) -> dict[str, str]:
    """Require an explicitly frozen, canonical regular behavior-tree XML file."""
    if not isinstance(value, str) or not value or not Path(value).is_absolute():
        raise ValueError("default_nav_to_pose_bt_xml must be an absolute canonical XML path")
    path = Path(value).resolve(strict=True)
    if str(path) != value or not path.is_file():
        raise ValueError("default_nav_to_pose_bt_xml must be an absolute canonical regular file")
    tree = ET.parse(path).getroot()
    if tree.tag != "root" or tree.find("BehaviorTree") is None:
        raise ValueError("default_nav_to_pose_bt_xml is not a behavior-tree XML document")
    return {"path": str(path), "sha256": sha256_file(path)}


def decode_behavior_tree_parameters(
    values: list[Any], expected: dict[str, str],
) -> dict[str, str]:
    if len(values) != 1:
        raise ValueError("behavior-tree read-back is incomplete")
    if values[0].type != 4:
        raise ValueError("behavior-tree path has the wrong ROS parameter type")
    observed = behavior_tree_record(values[0].string_value)
    if observed != expected:
        raise RuntimeError("effective behavior-tree path or contents differ from the frozen target")
    return observed


def sha256_tree(path: Path) -> str:
    """Hash asset names and bytes, independent of checkout/installation path."""
    digest = hashlib.sha256()
    files = sorted(item for item in path.rglob("*") if item.is_file())
    if not files:
        raise ValueError(f"asset tree is empty: {path}")
    for item in files:
        name = item.relative_to(path).as_posix().encode()
        digest.update(len(name).to_bytes(8, "big"))
        digest.update(name)
        digest.update(bytes.fromhex(sha256_file(item).removeprefix("sha256:")))
    return f"sha256:{digest.hexdigest()}"


def pose_matches(requested: dict[str, float], observed: dict[str, float]) -> bool:
    if not all(math.isfinite(value) for pose in (requested, observed) for value in pose.values()):
        return False
    distance = math.hypot(requested["x"] - observed["x"], requested["y"] - observed["y"])
    yaw_error = math.atan2(
        math.sin(requested["yaw"] - observed["yaw"]),
        math.cos(requested["yaw"] - observed["yaw"]),
    )
    return distance <= START_TOLERANCE_M and abs(yaw_error) <= START_YAW_TOLERANCE_RAD


def parse_gazebo_pose(output: str, model_name: str = "nav2_turtlebot4") -> dict[str, float]:
    """Parse Gazebo Harmonic's documented `gz model -m NAME --pose` output."""
    if not re.search(rf"- Name:\s*{re.escape(model_name)}\s*(?:\n|$)", output):
        raise ValueError("Gazebo did not return the requested robot model")
    match = re.search(
        r"- Pose \[ XYZ \(m\) \] \[ RPY \(rad\) \]:\s*"
        r"\[([^\]]+)\]\s*\[([^\]]+)\]",
        output,
    )
    if match is None:
        raise ValueError("Gazebo model pose is missing")
    # Harmonic source prints whitespace; older rendered documentation also
    # shows pipe separators. Both are the same XYZ/RPY representation.
    xyz = [float(value) for value in re.split(r"[\s|]+", match[1].strip())]
    rpy = [float(value) for value in re.split(r"[\s|]+", match[2].strip())]
    if len(xyz) != 3 or len(rpy) != 3 or not all(math.isfinite(v) for v in (*xyz, *rpy)):
        raise ValueError("Gazebo model pose is invalid")
    return {"x": xyz[0], "y": xyz[1], "yaw": rpy[2]}


def map_pose_is_free(map_message: Any, x: float, y: float) -> bool:
    """Reject unknown/occupied start and goal footprints in the actual ROS map."""
    info = map_message.info
    resolution = float(info.resolution)
    if not math.isfinite(resolution) or resolution <= 0:
        return False
    orientation = info.origin.orientation
    yaw = planar_yaw_from_quaternion(
        x=orientation.x, y=orientation.y, z=orientation.z, w=orientation.w
    )
    if not math.isfinite(yaw):
        return False
    dx = x - info.origin.position.x
    dy = y - info.origin.position.y
    local_x = math.cos(yaw) * dx + math.sin(yaw) * dy
    local_y = -math.sin(yaw) * dx + math.cos(yaw) * dy
    cell_x, cell_y = math.floor(local_x / resolution), math.floor(local_y / resolution)
    radius = math.ceil(MAP_CLEARANCE_M / resolution)
    for offset_y in range(-radius, radius + 1):
        for offset_x in range(-radius, radius + 1):
            if math.hypot(offset_x, offset_y) * resolution > MAP_CLEARANCE_M + resolution:
                continue
            px, py = cell_x + offset_x, cell_y + offset_y
            if not (0 <= px < info.width and 0 <= py < info.height):
                return False
            index = py * info.width + px
            if index >= len(map_message.data) or not 0 <= map_message.data[index] <= 20:
                return False
    return True


def asset_manifest(args: argparse.Namespace) -> dict[str, Any]:
    map_data = yaml.safe_load(args.map.read_text(encoding="utf-8"))
    image = args.map.parent / map_data["image"]
    params = yaml.safe_load(args.params.read_text(encoding="utf-8"))
    controller_parameters = params["controller_server"]["ros__parameters"]
    controller = controller_parameters["FollowPath"]
    expected = {"plugin": controller["plugin"], "vx_max": controller["vx_max"]}
    if expected["plugin"] != "nav2_mppi_controller::MPPIController":
        raise ValueError("Gazebo acceptance requires the MPPI FollowPath controller")
    if (
        isinstance(expected["vx_max"], bool)
        or not isinstance(expected["vx_max"], int | float)
        or not math.isfinite(expected["vx_max"])
        or expected["vx_max"] <= 0
    ):
        raise ValueError("FollowPath.vx_max must be a finite positive number")
    checker = controller_parameters.get("general_goal_checker", {})
    preset = {
        "visualize": controller.get("visualize", False),
        "regenerate_noises": controller.get("regenerate_noises", False),
        "xy_goal_tolerance": checker.get("xy_goal_tolerance", 0.25),
        "yaw_goal_tolerance": checker.get("yaw_goal_tolerance", 0.25),
        "stateful": checker.get("stateful", True),
        "goal_angle_activation_distance": controller.get("GoalAngleCritic", {}).get(
            "threshold_to_consider", 0.5,
        ),
    }
    validate_benchmark_preset(preset)
    behavior_tree = behavior_tree_record(
        params.get("bt_navigator", {}).get("ros__parameters", {}).get(BEHAVIOR_TREE_PARAMETER)
    )
    packages = {}
    for share in (args.sim_share, args.description_share):
        package = ET.parse(share / "package.xml").getroot()
        packages[package.findtext("name")] = package.findtext("version")
    bridge_path = args.sim_share / "configs" / "tb4_bridge.yaml"
    bridge_rows = yaml.safe_load(bridge_path.read_text(encoding="utf-8"))
    command_types = [row["ros_type_name"] for row in bridge_rows
                     if row.get("ros_topic_name", "").strip("/") == "cmd_vel"]
    if len(command_types) != 1 or command_types[0] not in (
        "geometry_msgs/msg/Twist", "geometry_msgs/msg/TwistStamped"
    ):
        raise ValueError("TB4 bridge must declare one supported cmd_vel message type")
    assets = {
        "map_yaml": sha256_file(args.map),
        "map_image": sha256_file(image),
        "world": sha256_file(args.world),
        "rendered_world": sha256_file(args.rendered_world),
        "launch": sha256_file(args.launch),
        "tb4_sim_tree": sha256_tree(args.sim_share),
        "tb4_description_tree": sha256_tree(args.description_share),
        "bridge_config": sha256_file(bridge_path),
        "behavior_tree": behavior_tree["sha256"],
    }
    # Fuel models are downloaded before collection. Their bytes are separate
    # from the world URI and must not silently change between control/candidate.
    fuel = Path.home() / ".gz" / "fuel"
    if fuel.is_dir() and any(item.is_file() for item in fuel.rglob("*")):
        assets["fuel_cache"] = sha256_tree(fuel)
    return {
        "schema_version": 1,
        "kind": "gazebo_runtime",
        "status": "INITIALIZING",
        "checks": {},
        "assets": assets,
        "params_sha256": sha256_file(args.params),
        "controller_expected": expected,
        "benchmark_preset_expected": preset,
        "behavior_tree_expected": behavior_tree,
        "command_velocity_type": command_types[0],
        "renderer": {"headless": True, "software": True, "engine": "ogre2"},
        "packages": packages,
        "world_partition": os.environ.get("GZ_PARTITION"),
        "start_pose": {
            "requested": {"x": args.start_x, "y": args.start_y, "yaw": args.start_yaw},
        },
    }


def _ros_pose(pose: Any) -> dict[str, float]:
    orientation = pose.orientation
    return {
        "x": float(pose.position.x),
        "y": float(pose.position.y),
        "yaw": planar_yaw_from_quaternion(
            x=orientation.x, y=orientation.y, z=orientation.z, w=orientation.w
        ),
    }


def _read_parameters_bounded(
    node: Any, client: Any, names: list[str], deadline: float, description: str,
) -> list[Any]:
    import rclpy
    from rcl_interfaces.srv import GetParameters

    while not client.service_is_ready() and time.monotonic() < deadline:
        rclpy.spin_once(node, timeout_sec=0.1)
    if not client.service_is_ready():
        raise TimeoutError(f"post-navigation {description} parameter service unavailable")
    request = GetParameters.Request()
    request.names = names
    future = client.call_async(request)
    while not future.done() and time.monotonic() < deadline:
        rclpy.spin_once(node, timeout_sec=0.1)
    if not future.done():
        future.cancel()
        raise TimeoutError(f"post-navigation {description} parameter read-back timed out")
    response = future.result()
    if response is None:
        raise RuntimeError(f"post-navigation {description} read-back is incomplete")
    return response.values


def verify_controller_unchanged(args: argparse.Namespace, manifest: dict[str, Any]) -> None:
    """Read the effective SUT again after navigation, before process cleanup."""
    import rclpy
    from rcl_interfaces.srv import GetParameters
    from rclpy.node import Node

    rclpy.init(args=[])
    node = Node("robotci_gazebo_controller_verification")
    client = node.create_client(GetParameters, "/controller_server/get_parameters")
    behavior_parameters = node.create_client(GetParameters, "/bt_navigator/get_parameters")
    deadline = time.monotonic() + 10
    try:
        observed, preset = decode_controller_parameters(_read_parameters_bounded(
            node, client, list(CONTROLLER_PARAMETER_NAMES), deadline, "controller",
        ))
        manifest["controller_after"] = observed
        manifest["benchmark_preset_after"] = preset
        manifest["params_sha256_after"] = sha256_file(args.params)
        if (observed != manifest["controller"] or preset != manifest["benchmark_preset"]
                or manifest["params_sha256_after"] != manifest["params_sha256"]):
            raise RuntimeError("controller configuration changed during navigation")
        manifest["checks"]["controller_stable"] = True
        manifest["checks"]["benchmark_preset_stable"] = True
        behavior_tree = decode_behavior_tree_parameters(_read_parameters_bounded(
            node, behavior_parameters, [BEHAVIOR_TREE_PARAMETER], deadline, "behavior-tree",
        ), manifest["behavior_tree_expected"])
        manifest["behavior_tree_after"] = behavior_tree
        if (behavior_tree != manifest["behavior_tree"]
                or behavior_tree["sha256"] != manifest["assets"]["behavior_tree"]):
            raise RuntimeError("behavior-tree configuration changed during navigation")
        manifest["checks"]["behavior_tree_stable"] = True
    finally:
        node.destroy_node()
        rclpy.shutdown()


def wait_until_ready(args: argparse.Namespace, manifest: dict[str, Any]) -> None:
    import rclpy
    from geometry_msgs.msg import PoseWithCovarianceStamped
    from lifecycle_msgs.srv import GetState
    from nav2_msgs.action import NavigateToPose
    from nav_msgs.msg import OccupancyGrid, Odometry
    from rcl_interfaces.srv import GetParameters
    from rclpy.action import ActionClient
    from rclpy.node import Node
    from rclpy.parameter import Parameter
    from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy, qos_profile_sensor_data
    from rosgraph_msgs.msg import Clock
    from sensor_msgs.msg import LaserScan
    from tf2_ros import Buffer, TransformListener

    deadline = time.monotonic() + args.timeout_sec
    rclpy.init(args=[])
    node = Node(
        "robotci_gazebo_readiness", parameter_overrides=[Parameter("use_sim_time", value=True)]
    )
    received: dict[str, tuple[Any, float]] = {}
    counts = {"clock": 0, "scan": 0, "odom": 0}
    clock_start: float | None = None
    clock_last = 0.0

    def remember(key: str, message: Any) -> None:
        nonlocal clock_start, clock_last
        received[key] = (message, time.monotonic())
        if key in counts:
            counts[key] += 1
        if key == "clock":
            clock_last = message.clock.sec + message.clock.nanosec / 1e9
            if clock_start is None:
                clock_start = clock_last

    subscriptions = [
        node.create_subscription(Clock, "/clock", lambda msg: remember("clock", msg),
                                 qos_profile_sensor_data),
        node.create_subscription(LaserScan, "/scan", lambda msg: remember("scan", msg),
                                 qos_profile_sensor_data),
        node.create_subscription(Odometry, "/odom", lambda msg: remember("odom", msg),
                                 qos_profile_sensor_data),
        node.create_subscription(PoseWithCovarianceStamped, "/amcl_pose",
                                 lambda msg: remember("amcl", msg),
                                 QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL,
                                            reliability=ReliabilityPolicy.RELIABLE)),
        node.create_subscription(OccupancyGrid, "/map", lambda msg: remember("map", msg),
                                 QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL,
                                            reliability=ReliabilityPolicy.RELIABLE)),
    ]
    initial = node.create_publisher(PoseWithCovarianceStamped, "/initialpose", 10)
    buffer = Buffer(node=node)
    listener = TransformListener(buffer, node)
    action = ActionClient(node, NavigateToPose, "/navigate_to_pose")
    clients = {name: node.create_client(GetState, f"/{name}/get_state")
               for name in REQUIRED_LIFECYCLE_NODES}
    parameters = node.create_client(GetParameters, "/controller_server/get_parameters")
    behavior_parameters = node.create_client(GetParameters, "/bt_navigator/get_parameters")
    velocity_parameters = {
        name: node.create_client(GetParameters, f"/{name}/get_parameters")
        for name in ("controller_server", "behavior_server", "velocity_smoother",
                     "collision_monitor")
    }

    def call(client: Any, request: Any) -> Any:
        if not client.service_is_ready():
            return None
        future = client.call_async(request)
        limit = min(deadline, time.monotonic() + 1.0)
        while not future.done() and time.monotonic() < limit:
            rclpy.spin_once(node, timeout_sec=0.05)
        if not future.done():
            future.cancel()
            return None
        return future.result()

    states: dict[str, int] = {}
    initialized = False
    last_initial = 0.0
    last_states = 0.0
    last_physical = 0.0
    physical_pose: dict[str, float] | None = None
    last_problem = "no fresh clock, scan or odometry"
    requested = manifest["start_pose"]["requested"]
    try:
        while time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.1)
            now = time.monotonic()
            fresh = all(key in received and now - received[key][1] < 3.0
                        for key in ("clock", "scan", "odom"))
            progressing = clock_start is not None and clock_last - clock_start >= 0.5
            sensors = counts["scan"] >= 3 and counts["odom"] >= 2
            if not (fresh and progressing and sensors):
                continue
            scan = received["scan"][0]
            if not scan.ranges or not any(math.isfinite(value) for value in scan.ranges):
                last_problem = "scan contains no observed finite ranges"
                continue
            odom = _ros_pose(received["odom"][0].pose.pose)
            if not all(math.isfinite(value) for value in odom.values()):
                last_problem = "odometry contains an invalid pose"
                continue
            if now - last_states >= 1.0:
                states = {}
                for name, client in clients.items():
                    response = call(client, GetState.Request())
                    if response is not None:
                        states[name] = int(response.current_state.id)
                last_states = time.monotonic()
            if states.get("amcl") != 3 or states.get("map_server") != 3:
                last_problem = f"localization lifecycle inactive: {states}"
                continue
            if not initialized and now - last_initial >= 1.0:
                message = PoseWithCovarianceStamped()
                message.header.frame_id = "map"
                message.header.stamp = node.get_clock().now().to_msg()
                message.pose.pose.position.x = args.start_x
                message.pose.pose.position.y = args.start_y
                message.pose.pose.orientation.z = math.sin(args.start_yaw / 2)
                message.pose.pose.orientation.w = math.cos(args.start_yaw / 2)
                message.pose.covariance[0] = 0.01
                message.pose.covariance[7] = 0.01
                message.pose.covariance[35] = 0.01
                initial.publish(message)
                last_initial = now
            if "amcl" not in received:
                last_problem = "AMCL has not acknowledged the initial pose"
                continue
            initialized = True
            observed = _ros_pose(received["amcl"][0].pose.pose)
            if not pose_matches(requested, observed):
                last_problem = f"localized start differs from requested start: {observed}"
                continue
            if "map" not in received or not all(
                map_pose_is_free(received["map"][0], x, y)
                for x, y in ((args.start_x, args.start_y), (args.goal_x, args.goal_y))
            ):
                last_problem = "start/goal footprint is occupied, unknown or outside the ROS map"
                continue
            if any(states.get(name) != 3 for name in REQUIRED_LIFECYCLE_NODES):
                last_problem = f"Nav2 lifecycle inactive: {states}"
                continue
            if not action.server_is_ready():
                last_problem = "navigate_to_pose action is unavailable"
                continue
            try:
                transform = buffer.lookup_transform("map", "base_footprint", rclpy.time.Time())
                tf_pose = _ros_pose(type("Pose", (), {
                    "position": transform.transform.translation,
                    "orientation": transform.transform.rotation,
                })())
                buffer.lookup_transform("odom", "base_footprint", rclpy.time.Time())
                scan_frame = received["scan"][0].header.frame_id
                buffer.lookup_transform("base_footprint", scan_frame, rclpy.time.Time())
            except Exception as exc:  # noqa: BLE001 - unavailable TF is a readiness condition
                last_problem = f"required TF unavailable: {exc}"
                continue
            if not pose_matches(requested, tf_pose):
                last_problem = f"TF start differs from requested start: {tf_pose}"
                continue
            if now - last_physical >= 1.0:
                try:
                    physical = subprocess.run(
                        ["gz", "model", "-m", "nav2_turtlebot4", "--pose"],
                        capture_output=True, text=True, timeout=min(4.0, max(0.1, deadline - now)),
                        check=True,
                    )
                    physical_pose = parse_gazebo_pose(physical.stdout)
                except (OSError, subprocess.SubprocessError, ValueError) as exc:
                    physical_pose = None
                    last_problem = f"independent Gazebo physical pose unavailable: {exc}"
                last_physical = time.monotonic()
            if physical_pose is None or not pose_matches(requested, physical_pose):
                last_problem = f"Gazebo physical start differs from request: {physical_pose}"
                continue
            request = GetParameters.Request()
            request.names = [*CONTROLLER_PARAMETER_NAMES, "use_sim_time"]
            response = call(parameters, request)
            if response is None or len(response.values) != len(CONTROLLER_PARAMETER_NAMES) + 1:
                last_problem = "controller parameters could not be read back"
                continue
            controller, preset = decode_controller_parameters(response.values[:-1])
            sim_time = response.values[-1]
            if (
                sim_time.type != 1
                or not sim_time.bool_value or controller != manifest["controller_expected"]
                or preset != manifest["benchmark_preset_expected"]
            ):
                raise RuntimeError(f"controller read-back does not match the SUT: {controller}")
            if sha256_file(args.params) != manifest["params_sha256"]:
                raise RuntimeError("controller YAML changed during runtime setup")
            request = GetParameters.Request()
            request.names = [BEHAVIOR_TREE_PARAMETER]
            response = call(behavior_parameters, request)
            if response is None:
                last_problem = "behavior-tree parameter service is not yet discovered"
                continue
            behavior_tree = decode_behavior_tree_parameters(
                response.values, manifest["behavior_tree_expected"],
            )
            expected_stamped = manifest["command_velocity_type"].endswith("TwistStamped")
            velocity_flags = {}
            velocity_discovered = True
            for name, client in velocity_parameters.items():
                request = GetParameters.Request()
                request.names = ["enable_stamped_cmd_vel"]
                response = call(client, request)
                if response is None:
                    velocity_discovered = False
                    last_problem = f"{name} parameter service is not yet discovered"
                    break
                if (len(response.values) != 1 or response.values[0].type != 1
                        or response.values[0].bool_value != expected_stamped):
                    raise RuntimeError(f"{name} cmd_vel type differs from the TB4 bridge")
                velocity_flags[name] = response.values[0].bool_value
            if not velocity_discovered:
                continue
            topic_types = dict(node.get_topic_names_and_types()).get("/cmd_vel", [])
            if topic_types != [manifest["command_velocity_type"]]:
                last_problem = f"cmd_vel ROS type differs from the bridge: {topic_types}"
                continue
            manifest.update({
                "status": "READY",
                "checks": {"clock_progressing": True, "scan_received": True,
                           "odom_received": True, "start_pose_verified": True,
                           "physical_start_verified": True, "map_footprints_free": True,
                           "physical_spawn_verified": True, "tf_verified": True,
                           "cmd_vel_type_verified": True,
                           "benchmark_preset_verified": True,
                           "behavior_tree_verified": True,
                           "required_tf": True, "nav2_active": True, "navigate_to_pose": True},
                "controller": controller,
                "benchmark_preset": preset,
                "behavior_tree": behavior_tree,
                "lifecycle": states,
                "clock": {"first": clock_start, "last": clock_last},
                "sensor_samples": counts,
                "odom": odom,
                "stamped_cmd_vel": velocity_flags,
            })
            manifest["start_pose"].update({"observed": observed, "tf": tf_pose,
                                           "gazebo": physical_pose})
            # A first warm-up may download Fuel assets while Gazebo starts.
            # READY requires real sensors/robot state, so capture the completed
            # cache here rather than an incomplete pre-launch download tree.
            completed_assets = asset_manifest(args)["assets"]
            if completed_assets["behavior_tree"] != behavior_tree["sha256"]:
                raise RuntimeError("behavior-tree contents changed during runtime setup")
            manifest["assets"] = completed_assets
            return
        raise TimeoutError(f"Gazebo readiness exceeded {args.timeout_sec}s: {last_problem}")
    finally:
        # Keep references alive until executor shutdown, then release native ROS resources.
        del listener, subscriptions
        action.destroy()
        node.destroy_node()
        rclpy.shutdown()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("start-x", "start-y", "start-yaw", "goal-x", "goal-y"):
        parser.add_argument(f"--{name}", type=float, required=True)
    for name in ("map", "world", "rendered-world", "params", "launch", "sim-share",
                 "description-share", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--timeout-sec", type=float, default=135)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    manifest: dict[str, Any] = {"schema_version": 1, "kind": "gazebo_runtime", "checks": {}}
    status = 3
    try:
        if not all(math.isfinite(getattr(args, name)) for name in
                   ("start_x", "start_y", "start_yaw", "goal_x", "goal_y", "timeout_sec")):
            raise ValueError("poses and readiness timeout must be finite")
        if args.timeout_sec <= 0:
            raise ValueError("readiness timeout must be positive")
        if args.verify_only:
            manifest = json.loads(args.output.read_text(encoding="utf-8"))
            verify_controller_unchanged(args, manifest)
        else:
            manifest = asset_manifest(args)
            wait_until_ready(args, manifest)
        status = 0
    except Exception as exc:  # noqa: BLE001 - persist unsuccessful setup evidence as well
        manifest.update({"status": "ERROR", "error": f"{type(exc).__name__}: {exc}"})
        print(manifest["error"], flush=True)
    finally:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(manifest, indent=2, allow_nan=False) + "\n",
                               encoding="utf-8")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
