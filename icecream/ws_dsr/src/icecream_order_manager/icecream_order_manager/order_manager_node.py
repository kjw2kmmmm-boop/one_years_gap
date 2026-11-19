import re
import threading
from dataclasses import dataclass

import rclpy
from rclpy.action import ActionServer, CancelResponse, GoalResponse
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node

from icecream_interfaces.action import ExecuteOrder, MeasureCup
from icecream_interfaces.msg import MotionDiagnostics, SystemTelemetry
from icecream_interfaces.srv import ExecuteTask

ERROR_NONE = 0
ERROR_MOTION = 1
ERROR_INVALID_ORDER = 2
ERROR_ABORTED = 3
ERROR_DIAMETER_OUT_OF_RANGE = 2

MIN_CUP_DIAMETER_MM = 40.0
MAX_CUP_DIAMETER_MM = 150.0

ALLOWED_FLAVORS = {"CHOCO", "STRAWBERRY", "VANILLA"}
_HEIGHT_PATTERN = re.compile(r"([0-9]+(?:\.[0-9]+)?)\s*mm")
_DIAMETER_PATTERN = re.compile(r"지름\s*측정\s*완료:\s*([0-9]+(?:\.[0-9]+)?)\s*mm")


@dataclass(frozen=True)
class MeasureMotionStep:
    """컵 측정 시나리오를 구성하는 단위 모션 스텝."""

    phase: str
    progress: float
    command: str
    timeout_sec: float
    sets_holding: bool = False
    clears_holding: bool = False


@dataclass(frozen=True)
class OrderMotionStep:
    """주문 오케스트레이션을 구성하는 단위 모션 스텝."""

    step_name: str
    order_status: str
    scoop_index: int
    command: str
    target: str
    message: str


class OrderManagerNode(Node):
    """주문·컵 측정 파라미터를 해석해 motion_manager를 순차 실행하는 오케스트레이터 노드."""

    def __init__(self) -> None:
        super().__init__("icecream_order_manager")
        self._cb_group = ReentrantCallbackGroup()
        self._robot_lock = threading.Lock()
        self._latest_cup_height_z = 0.0
        self._latest_contact_force = 0.0

        self._execute_task_client = self.create_client(
            ExecuteTask,
            "/execute_task",
            callback_group=self._cb_group,
        )
        self._diagnostics_sub = self.create_subscription(
            MotionDiagnostics,
            "/motion/diagnostics",
            self._on_diagnostics,
            10,
            callback_group=self._cb_group,
        )
        self._telemetry_sub = self.create_subscription(
            SystemTelemetry,
            "/dashboard/telemetry",
            self._on_telemetry,
            10,
            callback_group=self._cb_group,
        )

        self._execute_order_server = ActionServer(
            self,
            ExecuteOrder,
            "/execute_order",
            execute_callback=self._execute_order_callback,
            goal_callback=self._on_order_goal,
            cancel_callback=self._on_cancel,
            callback_group=self._cb_group,
        )
        self._measure_cup_server = ActionServer(
            self,
            MeasureCup,
            "/measure_cup",
            execute_callback=self._measure_cup_callback,
            goal_callback=self._on_measure_goal,
            cancel_callback=self._on_cancel,
            callback_group=self._cb_group,
        )
        self.get_logger().info(
            "OrderManagerNode ready (/execute_order, /measure_cup)"
        )

    def _on_diagnostics(self, msg: MotionDiagnostics) -> None:
        if msg.latest_cup_height_z > 0.0:
            self._latest_cup_height_z = float(msg.latest_cup_height_z)

    def _on_telemetry(self, msg: SystemTelemetry) -> None:
        self._latest_contact_force = abs(float(msg.tool_force_z))
        if msg.latest_cup_height_z > 0.0:
            self._latest_cup_height_z = float(msg.latest_cup_height_z)

    def _on_order_goal(self, goal_request: ExecuteOrder.Goal) -> GoalResponse:
        ice_type = (goal_request.ice_cream_type or "CUP").strip().upper()
        if ice_type == "SOFT":
            if self._robot_lock.locked():
                self.get_logger().warning("Rejected ExecuteOrder(SOFT) goal: robot is busy")
                return GoalResponse.REJECT
            return GoalResponse.ACCEPT

        if not goal_request.scoops:
            self.get_logger().warning("Rejected ExecuteOrder goal: empty scoops")
            return GoalResponse.REJECT
        for raw_flavor in goal_request.scoops:
            flavor = raw_flavor.strip().upper()
            if flavor not in ALLOWED_FLAVORS:
                self.get_logger().warning(
                    f"Rejected ExecuteOrder goal: unsupported flavor {raw_flavor!r}"
                )
                return GoalResponse.REJECT
        if self._robot_lock.locked():
            self.get_logger().warning("Rejected ExecuteOrder goal: robot is busy")
            return GoalResponse.REJECT
        return GoalResponse.ACCEPT

    def _on_measure_goal(self, goal_request: MeasureCup.Goal) -> GoalResponse:
        del goal_request
        if self._robot_lock.locked():
            self.get_logger().warning("Rejected MeasureCup goal: robot is busy")
            return GoalResponse.REJECT
        return GoalResponse.ACCEPT

    def _on_cancel(self, goal_handle) -> CancelResponse:
        del goal_handle
        return CancelResponse.ACCEPT

    def _call_motion_task(
        self,
        command: str,
        target: str = "",
        timeout_sec: float = 190.0,
    ) -> tuple[bool, int, str]:
        """motion_manager의 /execute_task 서비스를 동기적으로 대기 호출한다."""
        if not self._execute_task_client.wait_for_service(timeout_sec=3.0):
            return False, ERROR_MOTION, "motion_manager(/execute_task) 서비스를 찾을 수 없습니다."

        req = ExecuteTask.Request()
        req.command = command
        req.target = target

        done_event = threading.Event()
        future = self._execute_task_client.call_async(req)
        future.add_done_callback(lambda _f: done_event.set())

        if not done_event.wait(timeout=timeout_sec):
            return False, ERROR_MOTION, f"{command} 실행 시간이 초과되었습니다 ({timeout_sec:.0f}s)."

        exc = future.exception()
        if exc is not None:
            return False, ERROR_MOTION, f"{command} 호출 오류: {exc}"

        resp = future.result()
        return bool(resp.success), int(resp.error_code), str(resp.message)

    def _recover_home(self) -> None:
        """오류 또는 취소 후 안전하게 HOME 복귀를 시도한다."""
        try:
            self._call_motion_task("MOVE_HOME", timeout_sec=30.0)
        except Exception as exc:
            self.get_logger().warning(f"Safe home recovery failed: {exc}")

    def _return_plate_and_home(self) -> bool:
        """측정판을 원위치에 내려놓고 안전 상승 후 HOME으로 복귀한다."""
        for command in ("MOVE_TO_PLATE", "GRIPPER_RELEASE", "LIFT_Z", "MOVE_HOME"):
            ok, _err, msg = self._call_motion_task(command, timeout_sec=30.0)
            if not ok:
                self.get_logger().warning(
                    f"Safe plate return failed at {command}: {msg}"
                )
                return False
        return True

    @staticmethod
    def _build_measure_steps(measure_diameter: bool) -> list[MeasureMotionStep]:
        """컵 측정 Goal 옵션에 따른 단위 모션 시퀀스를 생성한다."""
        if not measure_diameter:
            return [
                MeasureMotionStep("APPROACHING", 10.0, "MOVE_HOME", 30.0),
                MeasureMotionStep("APPROACHING", 22.0, "MOVE_TO_PLATE", 30.0),
                MeasureMotionStep("APPROACHING", 35.0, "GRIPPER_GRAB", 30.0, sets_holding=True),
                MeasureMotionStep("APPROACHING", 50.0, "MOVE_CUP_Z", 30.0),
                MeasureMotionStep("PROBING_Z", 68.0, "CALIBRATE_CUP_Z", 190.0),
                MeasureMotionStep("RETRACTING", 80.0, "MOVE_TO_PLATE", 30.0),
                MeasureMotionStep("RETRACTING", 88.0, "GRIPPER_RELEASE", 30.0, clears_holding=True),
                MeasureMotionStep("RETRACTING", 93.0, "LIFT_Z", 30.0),
                MeasureMotionStep("RETRACTING", 97.0, "MOVE_HOME", 30.0),
            ]

        return [
            MeasureMotionStep("APPROACHING", 8.0, "MOVE_HOME", 30.0),
            MeasureMotionStep("APPROACHING", 16.0, "MOVE_TO_PLATE", 30.0),
            MeasureMotionStep("APPROACHING", 24.0, "GRIPPER_GRAB", 30.0, sets_holding=True),
            MeasureMotionStep("APPROACHING", 34.0, "MOVE_CUP_Z", 30.0),
            MeasureMotionStep("PROBING_Z", 46.0, "CALIBRATE_CUP_Z", 190.0),
            MeasureMotionStep("PROBING_Z", 56.0, "MOVE_TO_PLATE", 30.0),
            MeasureMotionStep("PROBING_Z", 64.0, "GRIPPER_RELEASE", 30.0, clears_holding=True),
            MeasureMotionStep("PROBING_Z", 70.0, "LIFT_Z", 30.0),
            MeasureMotionStep("PROBING_DIAMETER", 78.0, "PUSH_CUP_CORNER", 150.0),
            MeasureMotionStep("PROBING_DIAMETER", 88.0, "CALIBRATE_CUP_DIAMETER", 150.0),
            MeasureMotionStep("RETRACTING", 95.0, "MOVE_HOME", 30.0),
        ]

    def _build_order_steps(self, goal: ExecuteOrder.Goal) -> list[OrderMotionStep]:
        """주문 파라미터를 motion_manager 단위 모션 시퀀스로 변환한다."""
        ice_type = (goal.ice_cream_type or "CUP").strip().upper()
        if ice_type == "SOFT":
            hold_target = (
                f"{goal.cup_height_z:.2f},{goal.cup_diameter:.2f}"
                if goal.cup_height_z > 0.0 and goal.cup_diameter > 0.0
                else ""
            )
            return [
                OrderMotionStep(
                    step_name="MOVE_CUP_HOLD",
                    order_status="IN_PROGRESS",
                    scoop_index=0,
                    command="MOVE_CUP_HOLD",
                    target=hold_target,
                    message="컵 홀드 위치로 이동 중입니다.",
                ),
                OrderMotionStep(
                    step_name="GRIPPER_GRAB",
                    order_status="IN_PROGRESS",
                    scoop_index=0,
                    command="GRIPPER_GRAB",
                    target="",
                    message="그리퍼로 컵을 잡는 중입니다.",
                ),
                OrderMotionStep(
                    step_name="MOVE_CUP_MIDDLE",
                    order_status="SCOOPING",
                    scoop_index=0,
                    command="MOVE_CUP_MIDDLE",
                    target="",
                    message="중앙(스파이럴 시작) 위치로 이동 중입니다.",
                ),
                OrderMotionStep(
                    step_name="MOVE_CUP_SPIRAL",
                    order_status="SCOOPING",
                    scoop_index=0,
                    command="MOVE_CUP_SPRIAL",
                    target="",
                    message="소프트 아이스크림 스파이럴 제조 중입니다.",
                ),
                OrderMotionStep(
                    step_name="GRIPPER_RELEASE",
                    order_status="COMPLETING",
                    scoop_index=0,
                    command="GRIPPER_RELEASE",
                    target="",
                    message="컵을 내려놓고 그리퍼를 여는 중입니다.",
                ),
                OrderMotionStep(
                    step_name="MOVE_HOME",
                    order_status="COMPLETING",
                    scoop_index=0,
                    command="MOVE_HOME",
                    target="",
                    message="제조를 마치고 HOME으로 복귀 중입니다.",
                ),
            ]

        scoops = [s.strip().upper() for s in goal.scoops]
        steps: list[OrderMotionStep] = [
            OrderMotionStep(
                step_name="PREPARING_HOME",
                order_status="IN_PROGRESS",
                scoop_index=0,
                command="MOVE_HOME",
                target="",
                message="로봇 HOME 위치로 이동 중입니다.",
            ),
            OrderMotionStep(
                step_name="MOVING_TO_SCOOP",
                order_status="IN_PROGRESS",
                scoop_index=0,
                command="MOVE_TO_SCOOP",
                target="",
                message="스쿠프 파지 위치로 이동 중입니다.",
            ),
            OrderMotionStep(
                step_name="GRIPPING_SCOOP",
                order_status="IN_PROGRESS",
                scoop_index=0,
                command="GRIP_AND_LIFT",
                target="",
                message="스쿠프를 잡고 상승 중입니다.",
            ),
        ]

        # 단위 모션(스쿠핑/컵 투하/세척 등)이 추가되면 각 스쿱 루프에 바로 끼워 넣는다.
        for idx, flavor in enumerate(scoops, start=1):
            steps.append(
                OrderMotionStep(
                    step_name=f"SCOOP_{idx}_{flavor}",
                    order_status="SCOOPING",
                    scoop_index=idx,
                    command="MOVE_TO_FLAVOR",
                    target=flavor,
                    message=f"{idx}번 스쿱 ({flavor}) 제조 중입니다.",
                )
            )

        steps.append(
            OrderMotionStep(
                step_name="RETURNING_HOME",
                order_status="COMPLETING",
                scoop_index=0,
                command="MOVE_HOME",
                target="",
                message="제조를 마치고 HOME으로 복귀 중입니다.",
            )
        )
        return steps

    def _execute_order_callback(self, goal_handle) -> ExecuteOrder.Result:
        goal: ExecuteOrder.Goal = goal_handle.request
        result = ExecuteOrder.Result()

        if not self._robot_lock.acquire(blocking=False):
            goal_handle.abort()
            result.success = False
            result.error_code = ERROR_MOTION
            result.message = "다른 로봇 작업이 이미 실행 중입니다."
            return result

        try:
            steps = self._build_order_steps(goal)
            total_steps = len(steps)
            holding_item = False
            self.get_logger().info(
                f"Starting order {goal.order_code} (type={goal.ice_cream_type}): scoops={list(goal.scoops)}"
            )

            for idx, step in enumerate(steps):
                if goal_handle.is_cancel_requested:
                    if not holding_item:
                        self._recover_home()
                    goal_handle.canceled()
                    result.success = False
                    result.error_code = ERROR_ABORTED
                    result.message = f"주문 {goal.order_code} 실행이 취소되었습니다."
                    return result

                feedback = ExecuteOrder.Feedback()
                feedback.order_status = step.order_status
                feedback.current_step = step.step_name
                feedback.current_scoop_index = step.scoop_index
                feedback.progress_percent = float(round((idx / total_steps) * 100.0, 1))
                feedback.message = step.message
                goal_handle.publish_feedback(feedback)

                ok, err_code, msg = self._call_motion_task(step.command, step.target)
                if not ok:
                    if not holding_item and step.command != "MOVE_HOME":
                        self._recover_home()
                    goal_handle.abort()
                    result.success = False
                    result.error_code = err_code or ERROR_MOTION
                    result.message = f"[{step.step_name}] 실패: {msg}"
                    return result

                if step.command in {"GRIP_AND_LIFT", "GRIPPER_CUP", "GRIPPER_GRAB"}:
                    holding_item = True
                elif step.command in {"GRIPPER_RELEASE", "MOVE_HOME"}:
                    holding_item = False

            done_feedback = ExecuteOrder.Feedback()
            done_feedback.order_status = "COMPLETING"
            done_feedback.current_step = "COMPLETED"
            done_feedback.current_scoop_index = 0
            done_feedback.progress_percent = 100.0
            done_feedback.message = "아이스크림 제조가 완료되었습니다."
            goal_handle.publish_feedback(done_feedback)

            goal_handle.succeed()
            result.success = True
            result.error_code = ERROR_NONE
            result.message = f"주문 {goal.order_code} 제조 완료"
            return result
        finally:
            self._robot_lock.release()

    def _measure_cup_callback(self, goal_handle) -> MeasureCup.Result:
        goal: MeasureCup.Goal = goal_handle.request
        result = MeasureCup.Result()

        if not self._robot_lock.acquire(blocking=False):
            goal_handle.abort()
            result.success = False
            result.cup_available = False
            result.error_code = ERROR_MOTION
            result.message = "다른 로봇 작업이 이미 실행 중입니다."
            return result

        try:
            measure_diameter = bool(goal.measure_diameter)
            measure_steps = self._build_measure_steps(measure_diameter)
            measured_height = 0.0
            measured_diameter = 0.0
            holding_plate = False

            for step in measure_steps:
                if goal_handle.is_cancel_requested:
                    if not holding_plate:
                        self._recover_home()
                    goal_handle.canceled()
                    result.success = False
                    result.cup_available = False
                    result.error_code = ERROR_MOTION
                    result.message = (
                        "컵 측정이 취소되었습니다 (측정판 파지 상태 유지 - 수동 확인 필요)."
                        if holding_plate
                        else "컵 측정이 취소되었습니다."
                    )
                    return result

                feedback = MeasureCup.Feedback()
                feedback.current_phase = step.phase
                feedback.progress_percent = float(step.progress)
                feedback.current_contact_force = float(self._latest_contact_force)
                goal_handle.publish_feedback(feedback)

                target = ""
                if step.command == "CALIBRATE_CUP_DIAMETER" and measured_height > 0.0:
                    target = f"{measured_height:.2f}"

                ok, err_code, msg = self._call_motion_task(
                    step.command,
                    target=target,
                    timeout_sec=step.timeout_sec,
                )
                if not ok:
                    if step.command == "CALIBRATE_CUP_Z" and "감지되지 않았습니다" in msg:
                        returned = self._return_plate_and_home() if holding_plate else False
                        if returned:
                            holding_plate = False
                        else:
                            self._recover_home()
                        goal_handle.abort()
                        result.success = False
                        result.cup_available = False
                        result.error_code = ERROR_MOTION
                        result.message = (
                            "컵이 감지되지 않았습니다. 측정판을 원위치로 복귀했습니다."
                            if returned or not holding_plate
                            else f"[{step.command}] 컵 미감지 및 측정판 복귀 실패 (수동 확인 필요): {msg}"
                        )
                        return result

                    # 측정판을 잡고 있는 상태에서는 HOME 복귀 시 그리퍼가 열려 낙하할 수 있으므로 제자리 정지한다.
                    if not holding_plate and step.command != "MOVE_HOME":
                        self._recover_home()
                    goal_handle.abort()
                    result.success = False
                    result.cup_available = measured_height > 0.0
                    result.measured_height_z = measured_height
                    result.error_code = err_code or ERROR_MOTION
                    result.message = (
                        f"[{step.command}] 실패 (측정판 파지 상태 - 수동 확인 필요): {msg}"
                        if holding_plate
                        else f"[{step.command}] 실패: {msg}"
                    )
                    return result

                if step.sets_holding:
                    holding_plate = True
                if step.clears_holding:
                    holding_plate = False

                if step.command == "CALIBRATE_CUP_Z":
                    match = _HEIGHT_PATTERN.search(msg)
                    if match:
                        measured_height = float(match.group(1))
                    elif self._latest_cup_height_z > 0.0:
                        measured_height = float(self._latest_cup_height_z)
                elif step.command == "CALIBRATE_CUP_DIAMETER":
                    match = _DIAMETER_PATTERN.search(msg)
                    if match:
                        measured_diameter = float(match.group(1))
                    if measured_diameter <= 0.0:
                        self._recover_home()
                        goal_handle.abort()
                        result.success = False
                        result.cup_available = measured_height > 0.0
                        result.measured_height_z = measured_height
                        result.error_code = ERROR_MOTION
                        result.message = f"지름 측정 결과를 해석할 수 없습니다: {msg}"
                        return result
                    if not (MIN_CUP_DIAMETER_MM <= measured_diameter <= MAX_CUP_DIAMETER_MM):
                        self._recover_home()
                        goal_handle.abort()
                        result.success = False
                        result.cup_available = True
                        result.measured_height_z = measured_height
                        result.measured_diameter = measured_diameter
                        result.error_code = ERROR_DIAMETER_OUT_OF_RANGE
                        result.message = (
                            f"측정된 컵 지름({measured_diameter:.1f}mm)이 허용 규격 범위"
                            f"({MIN_CUP_DIAMETER_MM:.0f}~{MAX_CUP_DIAMETER_MM:.0f}mm)를 벗어났습니다."
                        )
                        return result

            if measured_height <= 0.0 and self._latest_cup_height_z > 0.0:
                measured_height = float(self._latest_cup_height_z)

            if not measure_diameter:
                measured_diameter = (
                    float(goal.expected_diameter) if goal.expected_diameter > 0.0 else 90.0
                )

            done_feedback = MeasureCup.Feedback()
            done_feedback.current_phase = "RETRACTING"
            done_feedback.progress_percent = 100.0
            done_feedback.current_contact_force = 0.0
            goal_handle.publish_feedback(done_feedback)

            goal_handle.succeed()
            result.success = True
            result.cup_available = True
            result.measured_height_z = measured_height
            result.measured_diameter = measured_diameter
            result.error_code = ERROR_NONE
            result.message = (
                f"컵 측정 완료 (높이 {measured_height:.2f}mm, 지름 {measured_diameter:.1f}mm)"
                if measure_diameter
                else f"컵 측정 완료 (높이 {measured_height:.2f}mm)"
            )
            return result
        finally:
            self._robot_lock.release()


def main(args=None) -> None:
    """주문/컵 측정 오케스트레이션 ROS2 노드 진입점."""
    rclpy.init(args=args)
    node = None
    executor = None
    try:
        node = OrderManagerNode()
        executor = MultiThreadedExecutor(num_threads=4)
        executor.add_node(node)
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        if executor is not None:
            executor.shutdown()
        if node is not None:
            node.destroy_node()
        rclpy.try_shutdown()


if __name__ == "__main__":
    main()
