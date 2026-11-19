"""ROS2 Python 3.12 환경에서 Action(ExecuteOrder / MeasureCup)을 호출하고
피드백과 최종 결과를 JSON 라인으로 stdout에 스트리밍하는 워커 스크립트."""

import argparse
import json
import signal
import sys

import rclpy
from rclpy.action import ActionClient

from icecream_interfaces.action import ExecuteOrder, MeasureCup


def _emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False), flush=True)


def _build_goal(action_type: str, goal_data: dict):
    if action_type == "execute_order":
        goal = ExecuteOrder.Goal()
        goal.order_code = str(goal_data.get("order_code", ""))
        goal.ice_cream_type = str(goal_data.get("ice_cream_type", "CUP"))
        goal.cup_height_z = float(goal_data.get("cup_height_z") or 0.0)
        goal.cup_diameter = float(goal_data.get("cup_diameter") or 0.0)
        goal.scoops = [str(s) for s in goal_data.get("scoops", [])]
        return ExecuteOrder, goal

    if action_type == "measure_cup":
        goal = MeasureCup.Goal()
        goal.measure_diameter = bool(goal_data.get("measure_diameter", False))
        goal.expected_diameter = float(goal_data.get("expected_diameter") or 90.0)
        return MeasureCup, goal

    raise ValueError(f"Unsupported action_type: {action_type}")


def _format_feedback(action_type: str, feedback_msg) -> dict:
    fb = feedback_msg.feedback
    if action_type == "execute_order":
        return {
            "type": "feedback",
            "order_status": str(fb.order_status),
            "current_step": str(fb.current_step),
            "current_scoop_index": int(fb.current_scoop_index),
            "progress_percent": float(fb.progress_percent),
            "message": str(fb.message),
        }
    return {
        "type": "feedback",
        "current_phase": str(fb.current_phase),
        "progress_percent": float(fb.progress_percent),
        "current_contact_force": float(fb.current_contact_force),
    }


def _format_result(action_type: str, res) -> dict:
    if action_type == "execute_order":
        return {
            "type": "result",
            "success": bool(res.success),
            "error_code": int(res.error_code),
            "message": str(res.message),
        }
    return {
        "type": "result",
        "success": bool(res.success),
        "cup_available": bool(res.cup_available),
        "measured_height_z": float(res.measured_height_z),
        "measured_diameter": float(res.measured_diameter),
        "error_code": int(res.error_code),
        "message": str(res.message),
    }


def run_action(
    action_type: str,
    action_name: str,
    goal_data: dict,
    wait_timeout: float,
    call_timeout: float,
) -> int:
    action_cls, goal_msg = _build_goal(action_type, goal_data)
    cancel_requested = False

    def _on_signal(_signum, _frame) -> None:
        nonlocal cancel_requested
        cancel_requested = True

    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)

    rclpy.init()
    node = None
    client = None
    try:
        node = rclpy.create_node(f"backend_{action_type}_client")
        client = ActionClient(node, action_cls, action_name)

        if not client.wait_for_server(timeout_sec=wait_timeout):
            _emit(
                {
                    "type": "result",
                    "success": False,
                    "error_code": 1,
                    "message": f"ROS2 action server '{action_name}' is unavailable",
                }
            )
            return 2

        send_future = client.send_goal_async(
            goal_msg,
            feedback_callback=lambda msg: _emit(_format_feedback(action_type, msg)),
        )
        rclpy.spin_until_future_complete(node, send_future, timeout_sec=wait_timeout)

        if not send_future.done():
            _emit(
                {
                    "type": "result",
                    "success": False,
                    "error_code": 1,
                    "message": f"Timed out waiting for '{action_name}' goal acceptance",
                }
            )
            return 3

        goal_handle = send_future.result()
        if goal_handle is None or not goal_handle.accepted:
            _emit(
                {
                    "type": "result",
                    "success": False,
                    "error_code": 1,
                    "message": f"ROS2 action '{action_name}' goal was rejected (busy or invalid)",
                }
            )
            return 4

        result_future = goal_handle.get_result_async()
        elapsed = 0.0
        step = 0.1
        sent_cancel = False

        while not result_future.done():
            if cancel_requested and not sent_cancel:
                sent_cancel = True
                goal_handle.cancel_goal_async()
            rclpy.spin_once(node, timeout_sec=step)
            elapsed += step
            if elapsed >= call_timeout:
                goal_handle.cancel_goal_async()
                _emit(
                    {
                        "type": "result",
                        "success": False,
                        "error_code": 3,
                        "message": f"ROS2 action '{action_name}' timed out after {call_timeout:.0f}s",
                    }
                )
                return 3

        wrapped = result_future.result()
        if wrapped is None:
            _emit(
                {
                    "type": "result",
                    "success": False,
                    "error_code": 1,
                    "message": f"ROS2 action '{action_name}' returned empty result",
                }
            )
            return 1

        _emit(_format_result(action_type, wrapped.result))
        return 0
    finally:
        if client is not None:
            client.destroy()
        if node is not None:
            node.destroy_node()
        rclpy.try_shutdown()


def main() -> int:
    parser = argparse.ArgumentParser(description="Call icecream_interfaces ROS2 Actions")
    parser.add_argument(
        "--action-type",
        required=True,
        choices=["execute_order", "measure_cup"],
    )
    parser.add_argument("--action-name", required=True)
    parser.add_argument("--goal", required=True, help="JSON serialized goal payload")
    parser.add_argument("--wait-timeout", type=float, default=3.0)
    parser.add_argument("--call-timeout", type=float, default=300.0)
    args = parser.parse_args()

    goal_data = json.loads(args.goal)
    return run_action(
        action_type=args.action_type,
        action_name=args.action_name,
        goal_data=goal_data,
        wait_timeout=args.wait_timeout,
        call_timeout=args.call_timeout,
    )


if __name__ == "__main__":
    sys.exit(main())
