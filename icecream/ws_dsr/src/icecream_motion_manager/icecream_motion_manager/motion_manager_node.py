import os
import threading

import DR_init
import rclpy
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node

from icecream_interfaces.msg import MotionDiagnostics
from icecream_interfaces.srv import ExecuteTask
from icecream_motion_manager.calibrate_cup_diameter import calibrate_cup_diameter
from icecream_motion_manager.calibrate_cup_z import calibration_cup_z
from icecream_motion_manager.grip_and_lift import grip_and_lift
from icecream_motion_manager.gripper import griper_cup, griper_grap, griper_release
from icecream_motion_manager.motion_utils import lift_relative_z, move_to_via
from icecream_motion_manager.move_cup_hold import move_cup_hold
from icecream_motion_manager.move_cup_middle import move_cup_middle
from icecream_motion_manager.move_cup_sprial import move_cup_sprial
from icecream_motion_manager.move_cup_z import move_cup_z
from icecream_motion_manager.move_home import ROBOT_ID, ROBOT_MODEL, move_home
from icecream_motion_manager.move_to_flavor import move_to_flavor
from icecream_motion_manager.move_to_plate import move_to_plate
from icecream_motion_manager.move_to_scoop import move_to_scoop
from icecream_motion_manager.push_cup_corner import push_cup_corner


# ExecuteTask.srv error_code 정의
ERROR_NONE = 0
ERROR_MOTION = 1
ERROR_UNKNOWN_COMMAND = 2
ERROR_ABORTED = 3

PLANNED_COMMANDS = {
    "DISPENSE_CUP",
    "CLEAN_SCOOP",
    "RELEASE_SCOOP",
}


class MotionManagerNode(Node):
    """ExecuteTask 서비스를 받아 로봇 모션을 수행하는 ROS2 노드."""

    def __init__(self) -> None:
        super().__init__("icecream_motion_manager")
        self._motion_lock = threading.Lock()
        self._latest_cup_height_z = 0.0
        self._latest_cup_diameter = 0.0
        self._task_handlers = {
            "MOVE_HOME": self._handle_move_home,
            "MOVE_TO_SCOOP": self._handle_move_to_scoop,
            "MOVE_CUP_Z": self._handle_move_cup_z,
            "MOVE_CUP_HOLD": self._handle_move_cup_hold,
            "MOVE_CUP_MIDDLE": self._handle_move_cup_middle,
            "MOVE_CUP_SPRIAL": self._handle_move_cup_sprial,
            "MOVE_CUP_SPIRAL": self._handle_move_cup_sprial,
            "MOVE_TO_PLATE": self._handle_move_to_plate,
            "MOVE_TO_VIA": self._handle_move_to_via,
            "MOVE_TO_FLAVOR": self._handle_move_to_flavor,
            "GRIP_AND_LIFT": self._handle_grip_and_lift,
            "LIFT_Z": self._handle_lift_z,
            "GRIPPER_RELEASE": self._handle_gripper_release,
            "GRIPPER_GRAB": self._handle_gripper_grab,
            "GRIPPER_GRAP": self._handle_gripper_grab,
            "GRIPPER_CUP": self._handle_gripper_cup,
            "CALIBRATE_CUP_Z": self._handle_calibrate_cup_z,
            "PUSH_CUP_CORNER": self._handle_push_cup_corner,
            "CALIBRATE_CUP_DIAMETER": self._handle_calibrate_cup_diameter,
        }
        self._diagnostics_pub = self.create_publisher(MotionDiagnostics, "/motion/diagnostics", 10)
        self._execute_task_srv = self.create_service(
            ExecuteTask,
            "/execute_task",
            self._execute_task_callback,
        )
        self._publish_diagnostics("IDLE", "", ERROR_NONE, "모션 매니저 준비 완료")
        self.get_logger().info("ExecuteTask service server ready on /execute_task")

    def _publish_diagnostics(
        self,
        system_state: str,
        command: str,
        error_code: int,
        message: str,
    ) -> None:
        msg = MotionDiagnostics()
        msg.timestamp = self.get_clock().now().to_msg()
        msg.system_state = system_state
        msg.current_command = command
        msg.error_code = int(error_code)
        msg.message = message
        msg.latest_cup_height_z = float(self._latest_cup_height_z)
        self._diagnostics_pub.publish(msg)

    def _handle_move_home(self, target: str) -> tuple[bool, int, str]:
        del target  # MOVE_HOME does not require a target identifier
        move_home()
        return True, ERROR_NONE, "HOME 이동 및 그리퍼 열기 완료"

    def _handle_move_to_scoop(self, target: str) -> tuple[bool, int, str]:
        del target  # MOVE_TO_SCOOP does not require a target identifier
        move_to_scoop()
        return True, ERROR_NONE, "스쿠프 위치 이동 완료"

    def _handle_move_cup_z(self, target: str) -> tuple[bool, int, str]:
        del target  # MOVE_CUP_Z does not require a target identifier
        move_cup_z()
        return True, ERROR_NONE, "컵 측정 위치(Z) 이동 완료"

    def _handle_move_cup_hold(self, target: str) -> tuple[bool, int, str]:
        cup_height: float | None = None
        cup_diameter: float | None = None

        if target:
            parts = [part.strip() for part in target.split(",")]
            if len(parts) != 2:
                return (
                    False,
                    ERROR_UNKNOWN_COMMAND,
                    f"잘못된 컵 크기 형식입니다(예: '115.0,90.0'): {target}",
                )
            try:
                cup_height = float(parts[0])
                cup_diameter = float(parts[1])
            except ValueError:
                return (
                    False,
                    ERROR_UNKNOWN_COMMAND,
                    f"잘못된 컵 크기 숫자입니다: {target}",
                )
        elif self._latest_cup_height_z > 0.0 and self._latest_cup_diameter > 0.0:
            cup_height = self._latest_cup_height_z
            cup_diameter = self._latest_cup_diameter

        move_cup_hold(cup_height=cup_height, cup_diameter=cup_diameter)
        return True, ERROR_NONE, (
            f"컵 홀드 위치 이동 완료 (높이 {cup_height:.1f}mm, 지름 {cup_diameter:.1f}mm)"
        )

    def _handle_move_cup_middle(self, target: str) -> tuple[bool, int, str]:
        del target  # MOVE_CUP_MIDDLE does not require a target identifier
        move_cup_middle()
        return True, ERROR_NONE, "컵 중간 위치(spiral) 이동 완료"

    def _handle_move_cup_sprial(self, target: str) -> tuple[bool, int, str]:
        del target  # MOVE_CUP_SPRIAL does not require a target identifier
        move_cup_sprial()
        return True, ERROR_NONE, "컵 스파이럴 이동 완료"

    def _handle_move_to_plate(self, target: str) -> tuple[bool, int, str]:
        del target  # MOVE_TO_PLATE does not require a target identifier
        move_to_plate()
        return True, ERROR_NONE, "측정판 이동 완료"

    def _handle_move_to_via(self, target: str) -> tuple[bool, int, str]:
        via_section = target.strip() or "via_point"
        move_to_via(via_section)
        return True, ERROR_NONE, f"경유 포인트({via_section}) 이동 완료"

    def _handle_move_to_flavor(self, target: str) -> tuple[bool, int, str]:
        try:
            flavor_name = move_to_flavor(target)
        except ValueError as exc:
            return False, ERROR_UNKNOWN_COMMAND, str(exc)
        return True, ERROR_NONE, f"{flavor_name} 위치 이동 완료"

    def _handle_grip_and_lift(self, target: str) -> tuple[bool, int, str]:
        del target  # GRIP_AND_LIFT does not require a target identifier
        grip_and_lift()
        return True, ERROR_NONE, "그리퍼 닫기 및 상승 완료"

    def _handle_lift_z(self, target: str) -> tuple[bool, int, str]:
        distance = 150.0
        if target:
            try:
                distance = float(target)
            except ValueError:
                return False, ERROR_UNKNOWN_COMMAND, f"잘못된 상승 거리 값입니다: {target}"
            if distance <= 0.0:
                return False, ERROR_UNKNOWN_COMMAND, f"상승 거리는 0보다 커야 합니다: {target}"
        lift_relative_z(distance_mm=distance)
        return True, ERROR_NONE, f"Z축 {distance:.1f}mm 안전 상승 완료"

    def _handle_gripper_release(self, target: str) -> tuple[bool, int, str]:
        del target
        griper_release()
        return True, ERROR_NONE, "그리퍼 열기 완료"

    def _handle_gripper_grab(self, target: str) -> tuple[bool, int, str]:
        del target
        griper_grap()
        return True, ERROR_NONE, "그리퍼 닫기 완료"

    def _handle_gripper_cup(self, target: str) -> tuple[bool, int, str]:
        del target
        griper_cup()
        return True, ERROR_NONE, "컵 파지용 그리퍼 닫기(DO3) 완료"

    def _handle_calibrate_cup_z(self, target: str) -> tuple[bool, int, str]:
        del target
        height = calibration_cup_z()
        if height is None:
            self._latest_cup_height_z = 0.0
            return False, ERROR_MOTION, "컵이 감지되지 않았습니다."
        self._latest_cup_height_z = float(height)
        return True, ERROR_NONE, f"컵 높이 측정 완료: {height:.2f}mm"

    def _handle_push_cup_corner(self, target: str) -> tuple[bool, int, str]:
        del target
        message = push_cup_corner()
        return True, ERROR_NONE, message

    def _handle_calibrate_cup_diameter(self, target: str) -> tuple[bool, int, str]:
        cup_height_mm: float | None = None
        if target:
            try:
                parsed = float(target)
            except ValueError:
                return False, ERROR_UNKNOWN_COMMAND, f"잘못된 컵 높이 값입니다: {target}"
            if parsed > 0.0:
                cup_height_mm = parsed
        elif self._latest_cup_height_z > 0.0:
            cup_height_mm = self._latest_cup_height_z

        measurement = calibrate_cup_diameter(
            cup_height_mm=cup_height_mm,
            allow_fallback=False,
        )
        if measurement is None:
            self._latest_cup_diameter = 0.0
            return False, ERROR_MOTION, "컵 측면 접촉이 감지되지 않았습니다."

        radius, diameter = measurement
        self._latest_cup_diameter = float(diameter)
        if cup_height_mm is not None:
            return (
                True,
                ERROR_NONE,
                f"컵 지름 측정 완료: {diameter:.1f}mm (반지름 {radius:.1f}mm, 높이 {cup_height_mm:.1f}mm 기준)",
            )
        return (
            True,
            ERROR_NONE,
            f"컵 지름 측정 완료: {diameter:.1f}mm (반지름 {radius:.1f}mm, 기본 Z 기준)",
        )

    def _execute_task_callback(
        self,
        request: ExecuteTask.Request,
        response: ExecuteTask.Response,
    ) -> ExecuteTask.Response:
        command = request.command.strip().upper()
        target = request.target.strip()
        self.get_logger().info(f"Received ExecuteTask request: command={command!r}, target={target!r}")

        handler = self._task_handlers.get(command)
        if handler is None:
            response.success = False
            response.error_code = ERROR_UNKNOWN_COMMAND
            if command in PLANNED_COMMANDS:
                response.message = f"아직 구현되지 않은 명령입니다: {command}"
            else:
                response.message = f"알 수 없는 명령입니다: {command}"
            return response

        if not self._motion_lock.acquire(blocking=False):
            response.success = False
            response.error_code = ERROR_MOTION
            response.message = "다른 모션 작업이 이미 실행 중입니다."
            return response

        try:
            self._publish_diagnostics(command, command, ERROR_NONE, f"{command} 실행 중")
            success, error_code, message = handler(target)
            response.success = success
            response.error_code = error_code
            response.message = message
            self._publish_diagnostics(
                "IDLE" if success else "ERROR",
                command,
                error_code,
                message,
            )
        except Exception as exc:
            self.get_logger().error(f"Motion execution failed for {command}: {exc}")
            response.success = False
            response.error_code = ERROR_MOTION
            response.message = str(exc)
            self._publish_diagnostics("ERROR", command, ERROR_MOTION, str(exc))
        finally:
            self._motion_lock.release()

        return response


def main(args=None) -> None:
    """모션 매니저 ROS2 서비스 노드 실행 진입점."""
    rclpy.init(args=args)
    dsr_node = None
    motion_node = None
    executor = None

    try:
        robot_id = os.getenv("ROBOT_ID", ROBOT_ID)
        robot_model = os.getenv("ROBOT_MODEL", ROBOT_MODEL)

        # DSR_ROBOT2는 내부에서 rclpy.spin_until_future_complete(DR_init.__dsr__node, ...)를 호출하며
        # 기본 전역 executor를 사용한다. 따라서 서비스 노드는 별도 SingleThreadedExecutor로 돌려 충돌을 방지한다.
        dsr_node = rclpy.create_node("icecream_dsr_client", namespace=robot_id)
        DR_init.__dsr__id = robot_id
        DR_init.__dsr__model = robot_model
        DR_init.__dsr__node = dsr_node

        #import DSR_ROBOT2  # noqa: F401 - 바인딩된 dsr_node로 서비스 클라이언트를 초기화한다.

        motion_node = MotionManagerNode()
        executor = SingleThreadedExecutor()
        executor.add_node(motion_node)
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        if executor is not None:
            executor.shutdown()
        if motion_node is not None:
            motion_node.destroy_node()
        if dsr_node is not None:
            dsr_node.destroy_node()
        rclpy.try_shutdown()


if __name__ == "__main__":
    main()
