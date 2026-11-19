import math
import os
from functools import partial

import rclpy
import tf2_ros
from rclpy.node import Node
from sensor_msgs.msg import JointState

from dsr_msgs2.srv import (
    GetCurrentPosx,
    GetJointTorque,
    GetRobotMode,
    GetRobotState,
    GetToolForce,
)
from icecream_interfaces.msg import MotionDiagnostics, SystemTelemetry

ROBOT_MODE_MAP = {
    0: "MANUAL",
    1: "AUTONOMOUS",
    2: "MEASURE",
}

EMERGENCY_STOP_STATES = {6, 7}
MOVING_STATES = {2, 7}
ERROR_STATES = {3, 5, 6, 9, 10, 15}


def _quat_to_rot_matrix(x: float, y: float, z: float, w: float) -> list[list[float]]:
    r00 = 1.0 - 2.0 * (y * y + z * z)
    r01 = 2.0 * (x * y - z * w)
    r02 = 2.0 * (x * z + y * w)
    r10 = 2.0 * (x * y + z * w)
    r11 = 1.0 - 2.0 * (x * x + z * z)
    r12 = 2.0 * (y * z - x * w)
    r20 = 2.0 * (x * z - y * w)
    r21 = 2.0 * (y * z + x * w)
    r22 = 1.0 - 2.0 * (x * x + y * y)
    return [
        [r00, r01, r02],
        [r10, r11, r12],
        [r20, r21, r22],
    ]


def _rot_matrix_to_zyz_deg(rot: list[list[float]]) -> list[float]:
    r22 = max(-1.0, min(1.0, rot[2][2]))
    beta = math.acos(r22)
    if abs(math.sin(beta)) > 1e-6:
        alpha = math.atan2(rot[1][2], rot[0][2])
        gamma = math.atan2(rot[2][1], -rot[2][0])
    else:
        alpha = 0.0
        gamma = (
            math.atan2(-rot[0][1], rot[0][0])
            if r22 > 0.0
            else math.atan2(rot[0][1], -rot[0][0])
        )
    return [math.degrees(alpha), math.degrees(beta), math.degrees(gamma)]


class SystemStatusNode(Node):
    """모션 진단, 실시간 TF/JointState, 두산 컨트롤러 상태를 취합해 /dashboard/telemetry로 발행한다."""

    def __init__(self) -> None:
        super().__init__("system_status_node")

        robot_id = os.getenv("ROBOT_ID", "dsr01").strip("/")
        dsr_prefix = f"/{robot_id}/dsr_controller2"
        joint_states_topic = f"/{robot_id}/joint_states"

        self._robot_mode = "MANUAL"
        self._is_emergency_stopped = False
        self._is_robot_moving = False
        self._js_moving = False
        self._last_joint_positions: list[float] | None = None
        self._current_tcp_pose = [0.0] * 6
        self._current_joint_angles = [0.0] * 6
        self._tcp_offset_in_flange = [0.0, 0.0, 0.0]
        self._last_flange_pose: tuple[list[float], list[list[float]]] | None = None
        self._joint_torques = [0.0] * 6
        self._tool_force_z = 0.0

        self._system_state = "IDLE"
        self._current_order_id = ""
        self._current_order_progress = 0.0
        self._latest_cup_height_z = 0.0
        self._cup_stock_warning = False
        self._active_error_code = 0

        self._pending: set[str] = set()

        self._tf_buffer = tf2_ros.Buffer()
        self._tf_listener = tf2_ros.TransformListener(self._tf_buffer, self)

        self._telemetry_pub = self.create_publisher(
            SystemTelemetry,
            "/dashboard/telemetry",
            10,
        )
        self._diagnostics_sub = self.create_subscription(
            MotionDiagnostics,
            "/motion/diagnostics",
            self._on_motion_diagnostics,
            10,
        )
        self._joint_states_sub = self.create_subscription(
            JointState,
            joint_states_topic,
            self._on_joint_states,
            10,
        )

        self._robot_mode_cli = self.create_client(
            GetRobotMode, f"{dsr_prefix}/system/get_robot_mode"
        )
        self._robot_state_cli = self.create_client(
            GetRobotState, f"{dsr_prefix}/system/get_robot_state"
        )
        self._current_posx_cli = self.create_client(
            GetCurrentPosx, f"{dsr_prefix}/aux_control/get_current_posx"
        )
        self._joint_torque_cli = self.create_client(
            GetJointTorque, f"{dsr_prefix}/aux_control/get_joint_torque"
        )
        self._tool_force_cli = self.create_client(
            GetToolForce, f"{dsr_prefix}/aux_control/get_tool_force"
        )

        # amovej/amovel + check_motion 사용 시 이동 중에도 dsr_controller2 서비스가 응답하므로 5Hz로 폴링하고,
        # 실제 좌표(/tf)와 이동 여부(/joint_states)는 10Hz로 발행한다.
        self._poll_timer = self.create_timer(0.2, self._poll_robot_status)
        self._publish_timer = self.create_timer(0.1, self._publish_telemetry)
        self.get_logger().info(
            f"SystemStatusNode ready: sub=(/motion/diagnostics, {joint_states_topic}, /tf), "
            f"pub=/dashboard/telemetry (dsr={dsr_prefix})"
        )

    def _on_motion_diagnostics(self, msg: MotionDiagnostics) -> None:
        if msg.system_state:
            self._system_state = str(msg.system_state)
        if msg.current_order_id:
            self._current_order_id = str(msg.current_order_id)
        if msg.current_order_progress > 0.0 or msg.current_order_id:
            self._current_order_progress = float(msg.current_order_progress)
        if msg.latest_cup_height_z > 0.0:
            self._latest_cup_height_z = float(msg.latest_cup_height_z)
        self._cup_stock_warning = bool(msg.cup_stock_warning)
        self._active_error_code = int(msg.error_code)

    def _on_joint_states(self, msg: JointState) -> None:
        if len(msg.position) < 6:
            return
        positions = [float(p) for p in msg.position[:6]]
        moving_by_vel = len(msg.velocity) >= 6 and any(
            abs(float(v)) > 0.002 for v in msg.velocity[:6]
        )
        moving_by_pos = (
            self._last_joint_positions is not None
            and any(abs(a - b) > 1e-4 for a, b in zip(positions, self._last_joint_positions))
        )
        self._last_joint_positions = positions
        self._current_joint_angles = [math.degrees(p) for p in positions]
        self._js_moving = moving_by_vel or moving_by_pos
        self._is_robot_moving = self._js_moving

    def _update_pose_from_tf(self) -> None:
        try:
            if not self._tf_buffer.can_transform("base_link", "link_6", rclpy.time.Time()):
                return
            tf_msg = self._tf_buffer.lookup_transform("base_link", "link_6", rclpy.time.Time())
        except Exception:
            return

        tr = tf_msg.transform.translation
        q = tf_msg.transform.rotation
        rot = _quat_to_rot_matrix(q.x, q.y, q.z, q.w)
        flange_xyz = [tr.x * 1000.0, tr.y * 1000.0, tr.z * 1000.0]
        self._last_flange_pose = (flange_xyz, rot)

        ox, oy, oz = self._tcp_offset_in_flange
        tcp_x = flange_xyz[0] + rot[0][0] * ox + rot[0][1] * oy + rot[0][2] * oz
        tcp_y = flange_xyz[1] + rot[1][0] * ox + rot[1][1] * oy + rot[1][2] * oz
        tcp_z = flange_xyz[2] + rot[2][0] * ox + rot[2][1] * oy + rot[2][2] * oz
        zyz = _rot_matrix_to_zyz_deg(rot)
        self._current_tcp_pose = [tcp_x, tcp_y, tcp_z, zyz[0], zyz[1], zyz[2]]

    def _call_async_if_ready(self, key: str, client, request, handler) -> None:
        if key in self._pending or not client.service_is_ready():
            return
        self._pending.add(key)
        future = client.call_async(request)
        future.add_done_callback(partial(self._handle_service_response, key, handler))

    def _handle_service_response(self, key: str, handler, future) -> None:
        self._pending.discard(key)
        try:
            result = future.result()
        except Exception:
            return
        if result is not None:
            handler(result)

    def _poll_robot_status(self) -> None:
        self._call_async_if_ready(
            "robot_mode",
            self._robot_mode_cli,
            GetRobotMode.Request(),
            self._on_robot_mode,
        )
        self._call_async_if_ready(
            "robot_state",
            self._robot_state_cli,
            GetRobotState.Request(),
            self._on_robot_state,
        )
        posx_req = GetCurrentPosx.Request()
        posx_req.ref = 0  # DR_BASE
        self._call_async_if_ready(
            "current_posx",
            self._current_posx_cli,
            posx_req,
            self._on_current_posx,
        )
        self._call_async_if_ready(
            "joint_torque",
            self._joint_torque_cli,
            GetJointTorque.Request(),
            self._on_joint_torque,
        )
        force_req = GetToolForce.Request()
        force_req.ref = 0  # DR_BASE
        self._call_async_if_ready(
            "tool_force",
            self._tool_force_cli,
            force_req,
            self._on_tool_force,
        )

    def _on_robot_mode(self, res: GetRobotMode.Response) -> None:
        if not res.success:
            return
        if not self._is_emergency_stopped:
            self._robot_mode = ROBOT_MODE_MAP.get(int(res.robot_mode), "MANUAL")

    def _on_robot_state(self, res: GetRobotState.Response) -> None:
        if not res.success:
            return
        state = int(res.robot_state)
        self._is_emergency_stopped = state in EMERGENCY_STOP_STATES
        self._is_robot_moving = self._js_moving or (state in MOVING_STATES)
        if self._is_emergency_stopped:
            self._robot_mode = "EMERGENCY_STOP"
            self._system_state = "ERROR"
            self._active_error_code = state
        elif state in ERROR_STATES and self._system_state == "IDLE":
            self._active_error_code = state

    def _on_current_posx(self, res: GetCurrentPosx.Response) -> None:
        if not res.success or not res.task_pos_info:
            return
        data = list(res.task_pos_info[0].data)
        if len(data) < 6:
            return
        tcp = [float(x) for x in data[:6]]
        # 정지 상태에서 DRCF TCP와 link_6 TF 간 오프셋을 보정해 이동 중 TF 기반 TCP도 정확히 맞춘다.
        if not self._js_moving and self._last_flange_pose is not None:
            flange_xyz, rot = self._last_flange_pose
            dx = tcp[0] - flange_xyz[0]
            dy = tcp[1] - flange_xyz[1]
            dz = tcp[2] - flange_xyz[2]
            self._tcp_offset_in_flange = [
                rot[0][0] * dx + rot[1][0] * dy + rot[2][0] * dz,
                rot[0][1] * dx + rot[1][1] * dy + rot[2][1] * dz,
                rot[0][2] * dx + rot[1][2] * dy + rot[2][2] * dz,
            ]
        if self._last_flange_pose is None:
            self._current_tcp_pose = tcp

    def _on_joint_torque(self, res: GetJointTorque.Response) -> None:
        if not res.success or len(res.jts) < 6:
            return
        self._joint_torques = [float(x) for x in res.jts[:6]]

    def _on_tool_force(self, res: GetToolForce.Response) -> None:
        if not res.success or len(res.tool_force) < 3:
            return
        self._tool_force_z = float(res.tool_force[2])

    def _publish_telemetry(self) -> None:
        self._update_pose_from_tf()

        msg = SystemTelemetry()
        msg.timestamp = self.get_clock().now().to_msg()
        msg.robot_mode = self._robot_mode
        msg.is_emergency_stopped = self._is_emergency_stopped
        msg.is_robot_moving = self._is_robot_moving
        msg.current_tcp_pose = self._current_tcp_pose
        msg.current_joint_angles = self._current_joint_angles
        msg.joint_torques = self._joint_torques
        msg.tool_force_z = self._tool_force_z
        msg.system_state = self._system_state
        msg.current_order_id = self._current_order_id
        msg.current_order_progress = float(self._current_order_progress)
        msg.latest_cup_height_z = float(self._latest_cup_height_z)
        msg.cup_stock_warning = self._cup_stock_warning
        msg.active_error_code = int(self._active_error_code)
        self._telemetry_pub.publish(msg)


def main(args=None) -> None:
    rclpy.init(args=args)
    node = None
    try:
        node = SystemStatusNode()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node is not None:
            node.destroy_node()
        rclpy.try_shutdown()


if __name__ == "__main__":
    main()
