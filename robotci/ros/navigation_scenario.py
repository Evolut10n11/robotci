from __future__ import annotations

import argparse
import math
import time
from pathlib import Path

import rclpy
from geometry_msgs.msg import PoseStamped
from nav2_simple_commander.robot_navigator import BasicNavigator, TaskResult

from robotci.evidence import NavigationEvidencePolicy, evaluate_navigation_success
from robotci.metrics import NavigationMetricsTracker, planar_yaw_from_quaternion
from robotci.replay import ReplayRecorder, default_replay_path, write_replay
from robotci.results import Pose2D, ScenarioResult, build_scenario_task, write_result

EXIT_PASS = 0
EXIT_FAIL = 1
EXIT_TIMEOUT = 2
EXIT_INFRA_ERROR = 3

FeedbackKey = tuple[int, int, int, int]


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


def _feedback_key(feedback: object) -> FeedbackKey:
    """Return fields that change only when Nav2 publishes fresh feedback."""
    pose_stamp = feedback.current_pose.header.stamp
    navigation_time = feedback.navigation_time
    return (
        int(pose_stamp.sec),
        int(pose_stamp.nanosec),
        int(navigation_time.sec),
        int(navigation_time.nanosec),
    )


def _yaw_from_orientation(orientation: object) -> float:
    """Convert a geometry_msgs quaternion into planar yaw."""
    return planar_yaw_from_quaternion(
        x=float(orientation.x),
        y=float(orientation.y),
        z=float(orientation.z),
        w=float(orientation.w),
    )


def _record_feedback(
    navigator: BasicNavigator,
    tracker: NavigationMetricsTracker,
    recorder: ReplayRecorder,
    now: float,
    last_feedback_key: FeedbackKey | None,
) -> FeedbackKey | None:
    feedback = navigator.getFeedback()
    if feedback is None:
        tracker.tick(now)
        return last_feedback_key

    feedback_key = _feedback_key(feedback)
    if feedback_key == last_feedback_key:
        # BasicNavigator caches the latest feedback object. Polling faster than
        # Nav2 publishes must not turn one message into many telemetry samples.
        tracker.tick(now)
        return last_feedback_key

    pose = feedback.current_pose.pose
    position = pose.position
    yaw = _yaw_from_orientation(pose.orientation)
    pose_is_valid = tracker.update(
        x=float(position.x),
        y=float(position.y),
        yaw=yaw,
        now=now,
        recoveries=int(feedback.number_of_recoveries),
    )
    if pose_is_valid:
        recorder.record(
            x=float(position.x),
            y=float(position.y),
            yaw=yaw,
            now=now,
        )
    return feedback_key


def run_navigation_scenario(
    scenario_name: str,
    start: Pose2D,
    goal: Pose2D,
    output: str | Path,
    timeout_sec: float,
    map_id: str = "unspecified",
    goal_tolerance_m: float = 0.25,
    min_feedback_samples: int = 1,
) -> int:
    started_at = time.monotonic()
    navigator: BasicNavigator | None = None
    tracker = NavigationMetricsTracker(
        start_x=start.x,
        start_y=start.y,
        started_at=started_at,
    )
    recorder = ReplayRecorder(
        scenario=scenario_name,
        start=start,
        goal=goal,
        started_at=started_at,
    )
    evidence_policy = NavigationEvidencePolicy(
        goal_tolerance_m=goal_tolerance_m,
        min_feedback_samples=min_feedback_samples,
    )
    status = "INFRA_ERROR"
    navigation_result = "UNKNOWN"
    reason_code: str | None = "runtime_not_completed"
    exit_code = EXIT_INFRA_ERROR

    try:
        rclpy.init(args=["--ros-args", "-p", "use_sim_time:=true"])
        node_name = f"robotci_{scenario_name.replace('-', '_')}"
        navigator = BasicNavigator(node_name=node_name)

        goal_pose = _pose_stamped(navigator, goal)

        # Runtime setup is not robot behavior. Start duration, replay timestamps,
        # timeout accounting, and stuck detection at goal dispatch.
        started_at = time.monotonic()
        tracker = NavigationMetricsTracker(
            start_x=start.x,
            start_y=start.y,
            started_at=started_at,
        )
        recorder = ReplayRecorder(
            scenario=scenario_name,
            start=start,
            goal=goal,
            started_at=started_at,
        )
        accepted = navigator.goToPose(goal_pose)

        if not accepted:
            status = "FAIL"
            navigation_result = "GOAL_REJECTED"
            reason_code = "goal_rejected"
            exit_code = EXIT_FAIL
        else:
            timed_out = False
            last_feedback_key: FeedbackKey | None = None

            while not navigator.isTaskComplete():
                now = time.monotonic()
                last_feedback_key = _record_feedback(
                    navigator,
                    tracker,
                    recorder,
                    now,
                    last_feedback_key,
                )

                if now - started_at >= timeout_sec:
                    navigator.cancelTask()
                    timed_out = True
                    break
                time.sleep(0.1)

            if timed_out:
                status = "TIMEOUT"
                navigation_result = "CANCELED_BY_TIMEOUT"
                reason_code = "timeout"
                exit_code = EXIT_TIMEOUT
            else:
                result = navigator.getResult()
                navigation_result = result.name

                if result == TaskResult.SUCCEEDED:
                    decision = evaluate_navigation_success(
                        metrics=tracker.snapshot(goal_x=goal.x, goal_y=goal.y),
                        telemetry_quality=tracker.telemetry_quality(),
                        policy=evidence_policy,
                    )
                    status = decision.status
                    reason_code = decision.reason_code
                    exit_code = {
                        "PASS": EXIT_PASS,
                        "FAIL": EXIT_FAIL,
                        "INFRA_ERROR": EXIT_INFRA_ERROR,
                    }[decision.status]
                elif result in {TaskResult.CANCELED, TaskResult.FAILED}:
                    status = "FAIL"
                    reason_code = (
                        "navigation_canceled"
                        if result == TaskResult.CANCELED
                        else "navigation_failed"
                    )
                    exit_code = EXIT_FAIL
                else:
                    status = "INFRA_ERROR"
                    reason_code = "unknown_navigation_result"
                    exit_code = EXIT_INFRA_ERROR

    except Exception as exc:  # noqa: BLE001 - scenario boundary must record infrastructure errors
        status = "INFRA_ERROR"
        navigation_result = f"{type(exc).__name__}: {exc}"
        reason_code = "runtime_exception"
        exit_code = EXIT_INFRA_ERROR
    finally:
        duration_sec = round(time.monotonic() - started_at, 3)
        metrics = tracker.snapshot(goal_x=goal.x, goal_y=goal.y)
        telemetry_quality = tracker.telemetry_quality()
        result = ScenarioResult(
            scenario=scenario_name,
            status=status,
            duration_sec=duration_sec,
            start=start,
            goal=goal,
            navigation_result=navigation_result,
            metrics=metrics,
            telemetry_quality=telemetry_quality,
            evidence_policy=evidence_policy,
            task=build_scenario_task(
                scenario=scenario_name,
                start=start,
                goal=goal,
                map_id=map_id,
            ),
            reason_code=reason_code,
        )
        result_path = write_result(result, output)
        replay = recorder.build(
            status=status,
            duration_sec=duration_sec,
            metrics=metrics,
            navigation_result=navigation_result,
            events=tracker.events,
        )
        replay_path = write_replay(replay, default_replay_path(result_path))

        print(f"RobotCI scenario: {scenario_name}")
        print(f"Status: {status}")
        print(f"Navigation result: {navigation_result}")
        print(f"Duration: {duration_sec:.3f}s")
        print(f"Path length: {metrics.path_length_m:.3f}m")
        print(f"Distance to goal: {metrics.distance_to_goal_m:.3f}m")
        print(f"Stuck events: {metrics.stuck_events}")
        print(f"Recoveries: {metrics.recoveries}")
        print(f"Valid pose samples: {telemetry_quality.valid_pose_samples}")
        print(f"Invalid pose samples: {telemetry_quality.invalid_pose_samples}")
        if reason_code is not None:
            print(f"Reason: {reason_code}")
        print(f"Result: {result_path}")
        print(f"Replay: {replay_path}")

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
        "--map-id",
        default="unspecified",
        help="Stable map name or content digest used for task compatibility",
    )
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
    parser.add_argument(
        "--goal-tolerance-m",
        type=float,
        default=0.25,
        help="Maximum measured distance to goal allowed for PASS",
    )
    parser.add_argument(
        "--min-feedback-samples",
        type=int,
        default=1,
        help="Minimum Nav2 feedback samples required for PASS",
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    start = Pose2D(x=args.start_x, y=args.start_y, yaw=args.start_yaw)
    goal = Pose2D(x=args.goal_x, y=args.goal_y, yaw=args.goal_yaw)
    return run_navigation_scenario(
        scenario_name=args.scenario,
        start=start,
        goal=goal,
        output=args.output,
        timeout_sec=args.timeout_sec,
        map_id=args.map_id,
        goal_tolerance_m=args.goal_tolerance_m,
        min_feedback_samples=args.min_feedback_samples,
    )


if __name__ == "__main__":
    raise SystemExit(main())
