"""ROS2 Python 3.12 환경에서 /dashboard/telemetry 토픽을 구독해 stdout JSON 라인으로 출력하는 워커."""

import argparse
import json
import sys

import rclpy
from icecream_interfaces.msg import SystemTelemetry
from rclpy.node import Node


class TelemetrySubscriberNode(Node):
    def __init__(self, topic_name: str) -> None:
        super().__init__("backend_telemetry_subscriber")
        self.create_subscription(
            SystemTelemetry,
            topic_name,
            self._on_telemetry,
            10,
        )

    def _on_telemetry(self, msg: SystemTelemetry) -> None:
        timestamp_sec = float(msg.timestamp.sec) + float(msg.timestamp.nanosec) / 1e9
        payload = {
            "timestamp": timestamp_sec,
            "robot_mode": str(msg.robot_mode),
            "is_emergency_stopped": bool(msg.is_emergency_stopped),
            "is_robot_moving": bool(msg.is_robot_moving),
            "current_tcp_pose": [round(float(v), 3) for v in msg.current_tcp_pose],
            "joint_torques": [round(float(v), 3) for v in msg.joint_torques],
            "tool_force_z": round(float(msg.tool_force_z), 3),
            "system_state": str(msg.system_state),
            "current_order_id": str(msg.current_order_id),
            "current_order_progress": round(float(msg.current_order_progress), 2),
            "latest_cup_height_z": round(float(msg.latest_cup_height_z), 3),
            "cup_stock_warning": bool(msg.cup_stock_warning),
            "active_error_code": int(msg.active_error_code),
        }
        print(json.dumps(payload, ensure_ascii=False), flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Subscribe to icecream_interfaces/msg/SystemTelemetry")
    parser.add_argument("--topic", default="/dashboard/telemetry")
    args = parser.parse_args()

    rclpy.init()
    node = None
    try:
        node = TelemetrySubscriberNode(args.topic)
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node is not None:
            node.destroy_node()
        rclpy.try_shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
