from __future__ import annotations

import argparse
import math
import time
from pathlib import Path

import rclpy
from geometry_msgs.msg import PoseStamped
from nav2_simple_commander.robot_navigator import BasicNavigator, TaskResult

from robotci.results import Pose2D, ScenarioResult, write_result

EXIT_PASS = 0
EXIT_FAIL = 1
EXIT_TIMEOUT = 2
EXIT_INFRA_ERROR = 3


def _pose_stamped(navigator: BasicNavigator, pose: Pose2D) -> PoseStamped:
    message = PoseStamped()
    message.header.frame_id = "map"
    message.header.stamp = navigator.get_clock().now().to_msg()
    message.pose.position.x = pose.x
    message.pose.position.y = pose.y

    half_yaw = pose.yaw / 2.0
    message.pose.orientation.z = math.sin(half_yaw)
    message.pose.orientation.w = math.cos(half_yaw)
    return message


def run_navigation_scenario(
    scenario_name: str,
    start: Pose2D,
    goal: Pose2D,
    output: str | Path,
    timeout_sec: float,
) -> int:
    started_at = time.monotonic()
    navigator: BasicNavigator | None = None
    status = "INFRA_ERROR"
    navigation_result = "UNKNOWN"
    exit_code = EXIT_INFRA_ERROR

    try:
        rclpy.init(args=["--ros-args", "-p", "use_sim_time:=true"])
        node_name = f"robotci_{scenario_name.replace('-', '_')}"
        navigator = BasicNavigator(node_name=node_name)

        goal_pose = _pose_stamped(navigator, goal)
        accepted = navigator.goToPose(goal_pose)

        if not accepted:
            status = "FAIL"
            navigation_result = "GOAL_REJECTED"
            exit_code = EXIT_FAIL
        else:
            timed_out = False

            while not navigator.isTaskComplete():
                if time.monotonic() - started_at >= timeout_sec:
                    navigator.cancelTask()
                    timed_out = True
                    break
                time.sleep(0.1)

            if timed_out:
                status = "TIMEOUT"
                navigation_result = "CANCELED_BY_TIMEOUT"
                exit_code = EXIT_TIMEOUT
            else:
                result = navigator.getResult()
                navigation_result = result.name

                if result == TaskResult.SUCCEEDED:
                    status = "PASS"
                    exit_code = EXIT_PASS
                elif result in {TaskResult.CANCELED, TaskResult.FAILED}:
                    status = "FAIL"
                    exit_code = EXIT_FAIL
                else:
                    status = "INFRA_ERROR"
                    exit_code = EXIT_INFRA_ERROR

    except Exception as exc:  # noqa: BLE001 - scenario boundary must record infrastructure errors
        status = "INFRA_ERROR"
        navigation_result = f"{type(exc).__name__}: {exc}"
        exit_code = EXIT_INFRA_ERROR
    finally:
        duration_sec = round(time.monotonic() - started_at, 3)
        result = ScenarioResult(
            scenario=scenario_name,
            status=status,
            duration_sec=duration_sec,
            start=start,
            goal=goal,
            navigation_result=navigation_result,
        )
        result_path = write_result(result, output)

        print(f"RobotCI scenario: {scenario_name}")
        print(f"Status: {status}")
        print(f"Navigation result: {navigation_result}")
        print(f"Duration: {duration_sec:.3f}s")
        print(f"Result: {result_path}")

        if navigator is not None:
            navigator.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()

    return exit_code


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one RobotCI Nav2 scenario")
    parser.add_argument("--scenario", required=True, help="Scenario name")
    parser.add_argument("--start-x", type=float, required=True)
    parser.add_argument("--start-y", type=float, required=True)
    parser.add_argument("--start-yaw", type=float, default=0.0)
    parser.add_argument("--goal-x", type=float, required=True)
    parser.add_argument("--goal-y", type=float, required=True)
    parser.add_argument("--goal-yaw", type=float, default=0.0)
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Path to the result JSON file",
    )
    parser.add_argument(
        "--timeout-sec",
        type=float,
        required=True,
        help="Maximum wall-clock time allowed for navigation",
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    start = Pose2D(x=args.start_x, y=args.start_y, yaw=args.start_yaw)
    goal = Pose2D(x=args.goal_x, y=args.goal_y, yaw=args.goal_yaw)
    return run_navigation_scenario(
        args.scenario,
        start,
        goal,
        args.output,
        args.timeout_sec,
    )


if __name__ == "__main__":
    raise SystemExit(main())
