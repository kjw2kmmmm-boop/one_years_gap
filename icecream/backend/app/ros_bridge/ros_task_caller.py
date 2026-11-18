"""ROS2 Python 3.12 환경에서 ExecuteTask 서비스를 호출하고 결과를 JSON으로 출력하는 워커 스크립트."""

import argparse
import json
import sys

import rclpy
from icecream_interfaces.srv import ExecuteTask


def call_service(
    service_name: str,
    command: str,
    target: str,
    wait_timeout: float,
    call_timeout: float,
) -> tuple[int, dict]:
    rclpy.init()
    node = None
    try:
        node = rclpy.create_node("backend_execute_task_client")
        client = node.create_client(ExecuteTask, service_name)

        if not client.wait_for_service(timeout_sec=wait_timeout):
            return 2, {
                "success": False,
                "error_code": 1,
                "message": f"ROS2 service '{service_name}' is unavailable",
            }

        req = ExecuteTask.Request()
        req.command = command
        req.target = target

        future = client.call_async(req)
        rclpy.spin_until_future_complete(node, future, timeout_sec=call_timeout)

        if not future.done():
            return 3, {
                "success": False,
                "error_code": 1,
                "message": f"ROS2 service '{service_name}' timed out after {call_timeout}s",
            }

        exc = future.exception()
        if exc is not None:
            return 1, {
                "success": False,
                "error_code": 1,
                "message": f"ROS2 service call failed: {exc}",
            }

        resp = future.result()
        return 0, {
            "success": bool(resp.success),
            "error_code": int(resp.error_code),
            "message": str(resp.message),
        }
    finally:
        if node is not None:
            node.destroy_node()
        rclpy.try_shutdown()


def main() -> int:
    parser = argparse.ArgumentParser(description="Call icecream_interfaces/srv/ExecuteTask")
    parser.add_argument("--service", default="/execute_task")
    parser.add_argument("--command", required=True)
    parser.add_argument("--target", default="")
    parser.add_argument("--wait-timeout", type=float, default=3.0)
    parser.add_argument("--call-timeout", type=float, default=30.0)
    args = parser.parse_args()

    exit_code, payload = call_service(
        service_name=args.service,
        command=args.command,
        target=args.target,
        wait_timeout=args.wait_timeout,
        call_timeout=args.call_timeout,
    )
    print(json.dumps(payload, ensure_ascii=False), flush=True)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
