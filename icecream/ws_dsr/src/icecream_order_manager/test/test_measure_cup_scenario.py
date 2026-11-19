"""Unit tests for the MeasureCup scenario in icecream_order_manager."""

from unittest.mock import patch

import rclpy

from icecream_interfaces.action import ExecuteOrder, MeasureCup
from icecream_order_manager.order_manager_node import (
    ERROR_DIAMETER_OUT_OF_RANGE,
    ERROR_MOTION,
    OrderManagerNode,
)


class _FakeGoalHandle:
    """Minimal stand-in for ServerGoalHandle during unit tests."""

    def __init__(self, goal: MeasureCup.Goal, cancel_at_step: int | None = None) -> None:
        self.request = goal
        self.cancel_at_step = cancel_at_step
        self.feedbacks: list[MeasureCup.Feedback] = []
        self.status: str | None = None

    @property
    def is_cancel_requested(self) -> bool:
        if self.cancel_at_step is None:
            return False
        return len(self.feedbacks) >= self.cancel_at_step

    def publish_feedback(self, feedback: MeasureCup.Feedback) -> None:
        self.feedbacks.append(feedback)

    def succeed(self) -> None:
        self.status = "SUCCEEDED"

    def abort(self) -> None:
        self.status = "ABORTED"

    def canceled(self) -> None:
        self.status = "CANCELED"


def _make_node() -> OrderManagerNode:
    return OrderManagerNode()


def test_measure_cup_full_scenario_sequence_and_results() -> None:
    """Verify full MeasureCup sequence including height, plate return, push, and diameter."""
    rclpy.init()
    node = _make_node()
    calls: list[tuple[str, str]] = []

    def fake_call(command: str, target: str = "", timeout_sec: float = 190.0):
        del timeout_sec
        calls.append((command, target))
        if command == "CALIBRATE_CUP_Z":
            return True, 0, "컵 높이 측정 완료: 115.00mm"
        if command == "CALIBRATE_CUP_DIAMETER":
            return True, 0, "컵 지름 측정 완료: 90.4mm (반지름 45.2mm, 높이 115.0mm 기준)"
        return True, 0, f"{command} OK"

    try:
        goal = MeasureCup.Goal(measure_diameter=True, expected_diameter=90.0)
        handle = _FakeGoalHandle(goal)
        with patch.object(node, "_call_motion_task", side_effect=fake_call):
            result = node._measure_cup_callback(handle)

        assert handle.status == "SUCCEEDED"
        assert result.success is True
        assert result.cup_available is True
        assert result.measured_height_z == 115.0
        assert result.measured_diameter == 90.4
        assert result.error_code == 0

        expected_commands = [
            ("MOVE_HOME", ""),
            ("MOVE_TO_PLATE", ""),
            ("GRIPPER_GRAB", ""),
            ("MOVE_CUP_Z", ""),
            ("CALIBRATE_CUP_Z", ""),
            ("MOVE_TO_PLATE", ""),
            ("GRIPPER_RELEASE", ""),
            ("LIFT_Z", ""),
            ("PUSH_CUP_CORNER", ""),
            ("CALIBRATE_CUP_DIAMETER", "115.00"),
            ("MOVE_HOME", ""),
        ]
        assert calls == expected_commands

        phases = [fb.current_phase for fb in handle.feedbacks]
        assert phases[0] == "APPROACHING"
        assert "PROBING_Z" in phases
        assert "PROBING_DIAMETER" in phases
        assert phases[-1] == "RETRACTING"
        assert handle.feedbacks[-1].progress_percent == 100.0
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


def test_measure_cup_height_only_skips_push_and_diameter() -> None:
    """Verify height-only mode skips corner push and diameter calibration."""
    rclpy.init()
    node = _make_node()
    calls: list[str] = []

    def fake_call(command: str, target: str = "", timeout_sec: float = 190.0):
        del target, timeout_sec
        calls.append(command)
        if command == "CALIBRATE_CUP_Z":
            return True, 0, "컵 높이 측정 완료: 85.50mm"
        return True, 0, f"{command} OK"

    try:
        goal = MeasureCup.Goal(measure_diameter=False, expected_diameter=78.0)
        handle = _FakeGoalHandle(goal)
        with patch.object(node, "_call_motion_task", side_effect=fake_call):
            result = node._measure_cup_callback(handle)

        assert handle.status == "SUCCEEDED"
        assert result.success is True
        assert result.cup_available is True
        assert result.measured_height_z == 85.5
        assert result.measured_diameter == 78.0
        assert "PUSH_CUP_CORNER" not in calls
        assert "CALIBRATE_CUP_DIAMETER" not in calls
        assert calls == [
            "MOVE_HOME",
            "MOVE_TO_PLATE",
            "GRIPPER_GRAB",
            "MOVE_CUP_Z",
            "CALIBRATE_CUP_Z",
            "MOVE_TO_PLATE",
            "GRIPPER_RELEASE",
            "LIFT_Z",
            "MOVE_HOME",
        ]
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


def test_measure_cup_no_cup_returns_plate_and_sets_unavailable() -> None:
    """Verify plate is returned safely when CALIBRATE_CUP_Z detects no cup."""
    rclpy.init()
    node = _make_node()
    calls: list[str] = []

    def fake_call(command: str, target: str = "", timeout_sec: float = 190.0):
        del target, timeout_sec
        calls.append(command)
        if command == "CALIBRATE_CUP_Z":
            return False, ERROR_MOTION, "컵이 감지되지 않았습니다."
        return True, 0, f"{command} OK"

    try:
        goal = MeasureCup.Goal(measure_diameter=True, expected_diameter=90.0)
        handle = _FakeGoalHandle(goal)
        with patch.object(node, "_call_motion_task", side_effect=fake_call):
            result = node._measure_cup_callback(handle)

        assert handle.status == "ABORTED"
        assert result.success is False
        assert result.cup_available is False
        assert result.error_code == ERROR_MOTION
        assert calls == [
            "MOVE_HOME",
            "MOVE_TO_PLATE",
            "GRIPPER_GRAB",
            "MOVE_CUP_Z",
            "CALIBRATE_CUP_Z",
            "MOVE_TO_PLATE",
            "GRIPPER_RELEASE",
            "LIFT_Z",
            "MOVE_HOME",
        ]
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


def test_measure_cup_diameter_out_of_range_recovers_home() -> None:
    """Verify out-of-range cup diameter aborts with error_code=2 after homing."""
    rclpy.init()
    node = _make_node()
    calls: list[str] = []

    def fake_call(command: str, target: str = "", timeout_sec: float = 190.0):
        del target, timeout_sec
        calls.append(command)
        if command == "CALIBRATE_CUP_Z":
            return True, 0, "컵 높이 측정 완료: 110.00mm"
        if command == "CALIBRATE_CUP_DIAMETER":
            return True, 0, "컵 지름 측정 완료: 25.0mm (반지름 12.5mm, 높이 110.0mm 기준)"
        return True, 0, f"{command} OK"

    try:
        goal = MeasureCup.Goal(measure_diameter=True, expected_diameter=90.0)
        handle = _FakeGoalHandle(goal)
        with patch.object(node, "_call_motion_task", side_effect=fake_call):
            result = node._measure_cup_callback(handle)

        assert handle.status == "ABORTED"
        assert result.success is False
        assert result.cup_available is True
        assert result.measured_diameter == 25.0
        assert result.error_code == ERROR_DIAMETER_OUT_OF_RANGE
        assert calls[-1] == "MOVE_HOME"
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


def test_soft_order_executes_spiral_release_and_home() -> None:
    """Verify SOFT order finishes with GRIPPER_RELEASE and MOVE_HOME after spiral."""
    rclpy.init()
    node = _make_node()
    calls: list[tuple[str, str]] = []

    def fake_call(command: str, target: str = "", timeout_sec: float = 190.0):
        del timeout_sec
        calls.append((command, target))
        return True, 0, f"{command} OK"

    try:
        goal = ExecuteOrder.Goal(
            order_code="ICE-20261119-999",
            ice_cream_type="SOFT",
            cup_height_z=88.45,
            cup_diameter=87.0,
            scoops=[],
        )
        handle = _FakeGoalHandle(goal)
        with patch.object(node, "_call_motion_task", side_effect=fake_call):
            result = node._execute_order_callback(handle)

        assert handle.status == "SUCCEEDED"
        assert result.success is True
        assert calls == [
            ("MOVE_CUP_HOLD", "88.45,87.00"),
            ("GRIPPER_GRAB", ""),
            ("MOVE_CUP_MIDDLE", ""),
            ("MOVE_CUP_SPRIAL", ""),
            ("GRIPPER_RELEASE", ""),
            ("MOVE_HOME", ""),
        ]
        assert [fb.current_step for fb in handle.feedbacks] == [
            "MOVE_CUP_HOLD",
            "GRIPPER_GRAB",
            "MOVE_CUP_MIDDLE",
            "MOVE_CUP_SPIRAL",
            "GRIPPER_RELEASE",
            "MOVE_HOME",
            "COMPLETED",
        ]
        assert handle.feedbacks[-1].progress_percent == 100.0
    finally:
        node.destroy_node()
        rclpy.try_shutdown()
