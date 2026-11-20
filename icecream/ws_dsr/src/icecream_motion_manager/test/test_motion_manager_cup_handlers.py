"""Unit tests for MotionManagerNode cup measurement and safe-lift handlers."""

import sys
from types import ModuleType
from unittest.mock import patch

import rclpy

from icecream_motion_manager import (
    calibrate_cup_diameter as calibrate_cup_diameter_mod,
    calibrate_cup_z as calibrate_cup_z_mod,
    motion_manager_node,
    motion_utils,
    move_cup_hold as move_cup_hold_mod,
    move_cup_z as move_cup_z_mod,
    move_home as move_home_mod,
    move_to_plate as move_to_plate_mod,
    pose_config as pose_config_mod,
    return_spoon as return_spoon_mod,
)
from icecream_motion_manager.motion_manager_node import (
    ERROR_MOTION,
    ERROR_NONE,
    ERROR_UNKNOWN_COMMAND,
    MotionManagerNode,
)


def test_lift_z_handler_validates_and_calls_helper() -> None:
    """Verify LIFT_Z accepts default or positive distance and rejects invalid targets."""
    rclpy.init()
    node = MotionManagerNode()
    try:
        with patch.object(motion_manager_node, "lift_relative_z") as mock_lift:
            ok, code, _msg = node._handle_lift_z("")
            assert ok is True
            assert code == ERROR_NONE
            mock_lift.assert_called_once_with(distance_mm=150.0)

        with patch.object(motion_manager_node, "lift_relative_z") as mock_lift:
            ok, code, _msg = node._handle_lift_z("120")
            assert ok is True
            assert code == ERROR_NONE
            mock_lift.assert_called_once_with(distance_mm=120.0)

        ok, code, _msg = node._handle_lift_z("-10")
        assert ok is False
        assert code == ERROR_UNKNOWN_COMMAND

        ok, code, _msg = node._handle_lift_z("abc")
        assert ok is False
        assert code == ERROR_UNKNOWN_COMMAND
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


def test_move_cup_hold_calculates_target_and_validates_arrival() -> None:
    """Verify move_cup_hold computes cup rim grip target from height and diameter."""
    moved_targets: list[list[float]] = []
    fake_dsr = ModuleType("DSR_ROBOT2")
    fake_dsr.DR_BASE = 0
    fake_dsr.check_motion = lambda: 0

    current_pose = [360.0, -145.0, 450.0, -124.86, 179.92, -163.43]
    fake_dsr.get_current_posx = lambda ref=0: (list(current_pose), 0)

    def fake_move_axis_sequence(target, vel, acc, label=""):
        del vel, acc, label
        moved_targets.append(list(target))
        current_pose[:3] = target[:3]

    with patch.dict(sys.modules, {"DSR_ROBOT2": fake_dsr}):
        with patch.object(move_cup_hold_mod, "CORNER_XY", (273.0, -225.0)):
            with patch.object(move_cup_hold_mod, "GROUND_Z", 0.0):
                with patch.object(move_cup_hold_mod, "GRIP_DEPTH", 10.0):
                    with patch.object(move_cup_hold_mod, "TCP_OFFSET", (-2.0, 35.0, 238.0)):
                        with patch.object(move_cup_hold_mod, "SAFE_Z", 410.0):
                            with patch.object(move_cup_hold_mod, "HEIGHT_RANGE", (60.0, 180.0)):
                                with patch.object(move_cup_hold_mod, "DIAMETER_RANGE", (40.0, 150.0)):
                                    with patch.object(
                                        move_cup_hold_mod,
                                        "get_section_config",
                                        return_value={},
                                    ):
                                        with patch.object(
                                            move_cup_hold_mod,
                                            "get_motion_entry",
                                            return_value=(
                                                [360.89, -145.12, 343.92, -124.86, 179.92, -163.43],
                                                80.0,
                                                80.0,
                                            ),
                                        ):
                                            with patch.object(
                                                move_cup_hold_mod,
                                                "load_cup_diameter_hit",
                                                return_value=None,
                                            ):
                                                with patch.object(
                                                    move_cup_hold_mod,
                                                    "move_axis_sequence",
                                                    side_effect=fake_move_axis_sequence,
                                                ):
                                                    result = move_cup_hold_mod.move_cup_hold(115.0, 90.0)

    # R=45 -> cup_x=318, cup_y=-180 -> grip=(363, -180, 105) + offset=(-2, 35, 238)
    assert result[:3] == [361.0, -145.0, 343.0]
    assert moved_targets == [result]


def test_move_cup_hold_works_with_default_measurement_settings() -> None:
    """Verify move_cup_hold runs with default cup-measurement settings without None errors."""
    fake_dsr = ModuleType("DSR_ROBOT2")
    fake_dsr.DR_BASE = 0
    fake_dsr.check_motion = lambda: 0
    current_pose = [367.0, 0.0, 424.5, -124.86, 179.92, -163.43]
    fake_dsr.get_current_posx = lambda ref=0: (list(current_pose), 0)

    def fake_move_axis_sequence(target, vel, acc, label=""):
        del vel, acc, label
        current_pose[:3] = target[:3]

    with patch.dict(sys.modules, {"DSR_ROBOT2": fake_dsr}):
        with patch.object(move_cup_hold_mod, "get_section_config", return_value={}):
            with patch.object(
                move_cup_hold_mod,
                "get_motion_entry",
                return_value=(
                    [360.89, -145.12, 343.92, -124.86, 179.92, -163.43],
                    80.0,
                    80.0,
                ),
            ):
                with patch.object(
                    move_cup_hold_mod,
                    "load_cup_diameter_hit",
                    return_value=None,
                ):
                    with patch.object(
                        move_cup_hold_mod,
                        "move_axis_sequence",
                        side_effect=fake_move_axis_sequence,
                    ):
                        result = move_cup_hold_mod.move_cup_hold(158.55, 90.0)

    expected_x = move_cup_hold_mod.CORNER_XY[0] + 90.0 + float(move_cup_hold_mod.TCP_OFFSET[0])
    expected_y = move_cup_hold_mod.CORNER_XY[1] + 45.0 + float(move_cup_hold_mod.TCP_OFFSET[1])
    expected_z = (
        move_cup_hold_mod.GROUND_Z
        + 158.55
        - move_cup_hold_mod.GRIP_DEPTH
        + float(move_cup_hold_mod.TCP_OFFSET[2])
    )
    assert result[:3] == [expected_x, expected_y, expected_z]


def test_handle_move_cup_hold_uses_target_or_latest_measurements() -> None:
    """Verify MotionManagerNode parses target or falls back to latest cup measurements."""
    rclpy.init()
    node = MotionManagerNode()
    try:
        node._latest_cup_height_z = 115.0
        node._latest_cup_diameter = 90.0
        with patch.object(motion_manager_node, "move_cup_hold") as mock_hold:
            ok, code, _msg = node._handle_move_cup_hold("")
            assert ok is True
            assert code == ERROR_NONE
            mock_hold.assert_called_once_with(cup_height=115.0, cup_diameter=90.0)

        with patch.object(motion_manager_node, "move_cup_hold") as mock_hold:
            ok, code, _msg = node._handle_move_cup_hold("120.5, 88.0")
            assert ok is True
            assert code == ERROR_NONE
            mock_hold.assert_called_once_with(cup_height=120.5, cup_diameter=88.0)

        ok, code, _msg = node._handle_move_cup_hold("120.5")
        assert ok is False
        assert code == ERROR_UNKNOWN_COMMAND
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


def test_calibrate_cup_z_stops_with_qstop_and_waits_for_ascent() -> None:
    """Verify calibration_cup_z uses stop_mode=1 on contact and waits for slow ascent."""
    stop_modes: list[int] = []
    current_z = 556.0
    motion_state = 0
    phase = "init"
    down_calls = 0

    class _FakeFuture:
        def __init__(self, success: bool = True) -> None:
            self._result = type("Res", (), {"success": success})()

        def done(self) -> bool:
            return True

        def result(self):
            return self._result

    class _FakeStopClient:
        def wait_for_service(self, timeout_sec: float = 3.0) -> bool:
            del timeout_sec
            return True

        def call_async(self, request):
            nonlocal motion_state, phase
            stop_modes.append(int(request.stop_mode))
            motion_state = 0
            phase = "stopped"
            return _FakeFuture(True)

    class _FakeNode:
        def create_client(self, srv_type, srv_name):
            del srv_type, srv_name
            return _FakeStopClient()

        def destroy_client(self, client) -> None:
            del client

    class _FakeRobot:
        DR_BASE = 0
        DR_MV_MOD_ABS = 0

        def check_motion(self) -> int:
            nonlocal down_calls, motion_state, current_z
            if phase == "descending":
                down_calls += 1
                motion_state = 1
                current_z = max(350.0, current_z - 1.0)
            elif phase == "ascending":
                down_calls += 1
                if down_calls < 3:
                    motion_state = 1
                else:
                    current_z = 556.0
                    motion_state = 0
            return motion_state

        def get_robot_state(self) -> int:
            return 1

        def get_current_posx(self, ref=0):
            del ref
            return ([338.57, -170.40, current_z, 136.05, 179.95, 135.81], 0)

        def get_tool_force(self, ref=0):
            del ref
            fz = 5.0 if phase == "descending" and current_z <= 355.0 else 0.0
            return [0.0, 0.0, fz, 0.0, 0.0, 0.0]

        def amovel(self, pos, vel=0.0, acc=0.0, ref=0, mod=0, radius=0.0):
            del pos, vel, acc, ref, mod, radius
            nonlocal phase, motion_state, down_calls
            if phase == "init":
                phase = "descending"
                motion_state = 1
            else:
                phase = "ascending"
                down_calls = 0
                motion_state = 1
            return 0

    fake_common = ModuleType("DR_common2")
    fake_common.posx = lambda coords: list(coords)

    with patch.dict(sys.modules, {"DR_common2": fake_common}):
        with patch.object(calibrate_cup_z_mod, "posx", lambda coords: list(coords)):
            with patch.object(calibrate_cup_z_mod.rclpy, "spin_until_future_complete"):
                with patch.object(calibrate_cup_z_mod.time, "sleep"):
                    with patch.object(
                        calibrate_cup_z_mod,
                        "_load_calibration_params",
                        return_value={
                            "gripper_mass_kg": 1.46,
                            "tip_offset_z": -238.0,
                            "ground_z": 0.0,
                            "min_z": 30.0,
                            "start_clear_mm": 8.0,
                            "down_speed": 20.0,
                            "down_acc": 5.0,
                            "up_speed": 100.0,
                            "up_acc": 15.0,
                            "force_limit": 2.0,
                            "start_abort_n": 4.0,
                            "max_seconds": 180.0,
                            "check_interval": 0.02,
                        },
                    ):
                        height = calibrate_cup_z_mod.calibration_cup_z(
                            robot=_FakeRobot(),
                            node=_FakeNode(),
                        )

    assert stop_modes == [1]
    assert height == 96.0


def test_ensure_default_tcp_resets_custom_tcp_and_registers_if_needed() -> None:
    """Verify ensure_default_tcp switches MANUAL->set_tcp/add_tcp->AUTONOMOUS when needed."""
    state = {"tcp": "tcptest", "mode": 1, "registered": set()}
    events: list[tuple[str, object]] = []

    fake_dsr = ModuleType("DSR_ROBOT2")
    fake_dsr.ROBOT_MODE_MANUAL = 0
    fake_dsr.ROBOT_MODE_AUTONOMOUS = 1
    fake_dsr.get_tcp = lambda: state["tcp"]
    fake_dsr.get_robot_mode = lambda: state["mode"]

    def fake_set_robot_mode(mode: int) -> int:
        events.append(("set_mode", mode))
        state["mode"] = mode
        return 0

    def fake_set_tcp(name: str) -> int:
        events.append(("set_tcp", name))
        if name not in state["registered"]:
            return -1
        state["tcp"] = name
        return 0

    def fake_add_tcp(name: str, pos: list[float]) -> int:
        events.append(("add_tcp", (name, list(pos))))
        state["registered"].add(name)
        return 0

    fake_dsr.set_robot_mode = fake_set_robot_mode
    fake_dsr.set_tcp = fake_set_tcp
    fake_dsr.add_tcp = fake_add_tcp

    with patch.dict(sys.modules, {"DSR_ROBOT2": fake_dsr}):
        with patch.object(motion_utils, "get_section_config", return_value={}):
            restored = motion_utils.ensure_default_tcp()
            assert restored == "flange_default"
            assert state["tcp"] == "flange_default"
            assert state["mode"] == 1
            assert events == [
                ("set_mode", 0),
                ("set_tcp", "flange_default"),
                ("add_tcp", ("flange_default", [0.0, 0.0, 0.0, 0.0, 0.0, 0.0])),
                ("set_tcp", "flange_default"),
                ("set_mode", 1),
            ]

            # 이미 기본 TCP면 모드 전환 없이 즉시 반환
            events.clear()
            assert motion_utils.ensure_default_tcp() == "flange_default"
            assert events == []


def test_move_home_calls_ensure_default_tcp() -> None:
    """Verify move_home restores default TCP before movel homing and opens gripper."""
    calls: list[tuple] = []
    fake_dsr = ModuleType("DSR_ROBOT2")
    fake_dsr.DR_BASE = 0
    fake_dsr.DR_MV_MOD_ABS = 0
    fake_dsr.posx = lambda *coords: tuple(coords)

    def fake_movel(pos, vel=0.0, acc=0.0, ref=0, mod=0):
        calls.append(("movel", pos, vel, acc, ref, mod))
        return 0

    fake_dsr.movel = fake_movel

    home_pose = [367.47, 7.96, 423.09, 96.96, 179.96, 96.72]
    with patch.dict(sys.modules, {"DSR_ROBOT2": fake_dsr}):
        with patch.object(
            move_home_mod,
            "get_motion_entry",
            return_value=(home_pose, 70.0, 70.0),
        ):
            with patch.object(
                move_home_mod,
                "ensure_default_tcp",
                side_effect=lambda: calls.append(("tcp",)),
            ):
                with patch.object(
                    move_home_mod,
                    "grip_release",
                    side_effect=lambda: calls.append(("release",)),
                ):
                    move_home_mod.move_home()

    assert calls == [
        ("tcp",),
        ("movel", tuple(home_pose), 70.0, 70.0, 0, 0),
        ("release",),
    ]


def test_move_blending_builds_posb_segments_with_zero_last_radius() -> None:
    """Verify motion_utils.move_blending converts waypoints to posb and forces last radius=0."""
    captured: list[tuple] = []

    class _FakePosb:
        def __init__(self, seg_type, posx1, posx2=None, radius=0.0) -> None:
            self._seg_type = seg_type
            self._posx1 = posx1
            self._posx2 = posx2
            self._radius = radius

    fake_common = ModuleType("DR_common2")
    fake_common.posb = _FakePosb
    fake_common.posx = lambda *coords: tuple(coords)

    fake_dsr = ModuleType("DSR_ROBOT2")
    fake_dsr.DR_BASE = 0
    fake_dsr.DR_LINE = 0
    fake_dsr.DR_MV_MOD_ABS = 0

    def fake_dsr_amoveb(seg_list, vel=0.0, acc=0.0, ref=0, mod=0, time=0.0):
        captured.append((seg_list, vel, acc, ref, mod, time))
        return 0

    fake_dsr.amoveb = fake_dsr_amoveb

    p1 = [400.0, -150.0, 450.0, 0.0, 180.0, 0.0]
    p2 = [350.0, -170.0, 450.0, 0.0, 180.0, 0.0]
    p3 = [350.0, -170.0, 320.0, 0.0, 180.0, 0.0]

    with patch.dict(sys.modules, {"DR_common2": fake_common, "DSR_ROBOT2": fake_dsr}):
        with patch.object(motion_utils, "wait_for_motion") as mock_wait:
            motion_utils.move_blending(
                [(p1, 25.0), p2, (p3, 15.0)],
                vel=80.0,
                acc=80.0,
                default_radius=20.0,
            )

    mock_wait.assert_called_once()
    assert len(captured) == 1
    seg_list, vel, acc, ref, mod, time_sec = captured[0]
    assert (vel, acc, ref, mod, time_sec) == (80.0, 80.0, 0, 0, 0.0)
    assert [s._radius for s in seg_list] == [25.0, 20.0, 0.0]
    assert [s._posx1 for s in seg_list] == [tuple(p1), tuple(p2), tuple(p3)]


def test_move_to_plate_uses_move_blending_with_safe_radii() -> None:
    """Verify move_to_plate routes X->Y->Z waypoints through move_blending with clamped radii."""
    blended_calls: list[tuple] = []
    fake_dsr = ModuleType("DSR_ROBOT2")
    fake_dsr.DR_BASE = 0
    fake_dsr.DR_MV_MOD_ABS = 0
    fake_dsr.amovel = lambda *args, **kwargs: 0
    fake_dsr.posx = lambda *coords: tuple(coords)
    fake_dsr.get_current_posx = lambda ref=0: (
        [338.57, -170.40, 556.32, 136.05, 179.95, 135.81],
        0,
    )

    def fake_move_blending(waypoints, vel=0.0, acc=0.0, label=""):
        blended_calls.append((waypoints, vel, acc, label))

    target = [573.59, -135.38, 249.19, -121.31, 179.81, -121.34]
    with patch.dict(sys.modules, {"DSR_ROBOT2": fake_dsr}):
        with patch.object(motion_utils, "get_motion_via", return_value=None):
            with patch.object(
                motion_utils,
                "get_motion_entry",
                return_value=(target, 80.0, 80.0),
            ):
                with patch.object(
                    motion_utils,
                    "get_section_config",
                    return_value={"blend_radius": 20.0},
                ):
                    with patch.object(
                        motion_utils,
                        "move_blending",
                        side_effect=fake_move_blending,
                    ):
                        move_to_plate_mod.move_to_plate()

    assert len(blended_calls) == 1
    waypoints, vel, acc, label = blended_calls[0]
    assert (vel, acc, label) == (80.0, 80.0, "측정판")
    # ΔX=235.02, ΔY=35.02, ΔZ=307.13 -> 두 번째 코너는 ΔY*0.4 = 14.01로 클램프, 마지막은 0.0
    assert [wp[0][:3] for wp in waypoints] == [
        [573.59, -170.40, 556.32],
        [573.59, -135.38, 556.32],
        [573.59, -135.38, 249.19],
    ]
    assert [wp[1] for wp in waypoints] == [14.01, 14.01, 0.0]


def test_move_axis_sequence_uses_move_blending_20mm() -> None:
    """Verify move_axis_sequence delegates waypoints to move_blending with 20mm radius when enabled."""
    calls: list[tuple] = []
    fake_dsr = ModuleType("DSR_ROBOT2")
    fake_dsr.DR_BASE = 0
    fake_dsr.DR_MV_MOD_ABS = 0
    fake_dsr.amovel = lambda *args, **kwargs: 0
    fake_dsr.posx = lambda *coords: tuple(coords)
    fake_dsr.get_current_posx = lambda ref=0: (
        [200.0, 0.0, 450.0, 0.0, 180.0, 0.0],
        0,
    )

    def fake_move_blending(waypoints, vel=0.0, acc=0.0, label=""):
        calls.append((waypoints, vel, acc, label))

    target = [360.0, -180.0, 340.0, -124.86, 179.92, -163.43]
    with patch.dict(sys.modules, {"DSR_ROBOT2": fake_dsr}):
        with patch.object(motion_utils, "move_blending", side_effect=fake_move_blending):
            motion_utils.move_axis_sequence(
                target,
                vel=80.0,
                acc=80.0,
                label="테스트",
                use_blending=True,
            )

    assert len(calls) == 1
    waypoints, vel, acc, label = calls[0]
    assert (vel, acc, label) == (80.0, 80.0, "테스트")
    assert [wp[0][:3] for wp in waypoints] == [
        [360.0, 0.0, 450.0],
        [360.0, -180.0, 450.0],
        [360.0, -180.0, 340.0],
    ]
    assert [wp[1] for wp in waypoints] == [20.0, 20.0, 0.0]


def test_move_axis_sequence_defaults_to_sequential_amovel() -> None:
    """Verify move_axis_sequence uses sequential amovel by default (e.g. move_cup_hold)."""
    amovel_calls: list[tuple] = []
    fake_dsr = ModuleType("DSR_ROBOT2")
    fake_dsr.DR_BASE = 0
    fake_dsr.DR_MV_MOD_ABS = 0
    fake_dsr.posx = lambda *coords: tuple(coords)
    fake_dsr.get_current_posx = lambda ref=0: (
        [367.47, 7.96, 423.09, -116.45, 179.97, -116.44],
        0,
    )

    def fake_amovel(pos, vel=0.0, acc=0.0, ref=0, mod=0):
        amovel_calls.append((pos, vel, acc, ref, mod))
        return 0

    fake_dsr.amovel = fake_amovel

    target = [360.0, -181.5, 316.45, -124.86, 179.92, -163.43]
    with patch.dict(sys.modules, {"DSR_ROBOT2": fake_dsr}):
        with patch.object(motion_utils, "wait_for_motion") as mock_wait:
            with patch.object(
                motion_utils,
                "move_blending",
                side_effect=AssertionError("move_blending should not be called by default"),
            ):
                motion_utils.move_axis_sequence(
                    target,
                    vel=80.0,
                    acc=80.0,
                    label="컵 크기 기반 홀드 위치",
                )

    assert len(amovel_calls) == 3
    assert mock_wait.call_count == 3
    assert [c[0][:3] for c in amovel_calls] == [
        (360.0, 7.96, 423.09),
        (360.0, -181.5, 423.09),
        (360.0, -181.5, 316.45),
    ]


def test_move_cup_z_uses_sequential_movel_z_then_xy() -> None:
    """Verify move_cup_z calls movel for Z first and then target XY regardless of start Z."""
    for start_z in (284.72, 628.0):
        recorded: list[tuple[float, ...]] = []
        fake_dsr = ModuleType("DSR_ROBOT2")
        fake_dsr.DR_BASE = 0
        fake_dsr.DR_MV_MOD_ABS = 0
        fake_dsr.posx = lambda *coords: tuple(coords)
        fake_dsr.get_current_posx = lambda ref=0: (
            [578.45, -222.64, start_z, 54.96, -180.0, 54.72],
            0,
        )

        def fake_movel(pos, vel=0.0, acc=0.0, ref=0, mod=0):
            del vel, acc, ref, mod
            recorded.append(pos)
            return 0

        fake_dsr.movel = fake_movel

        target = [338.57, -170.40, 556.32, 136.05, 179.95, 135.81]
        with patch.dict(sys.modules, {"DSR_ROBOT2": fake_dsr}):
            with patch.object(move_cup_z_mod, "get_motion_via", return_value=None):
                with patch.object(
                    move_cup_z_mod,
                    "get_motion_entry",
                    return_value=(target, 80.0, 80.0),
                ):
                    move_cup_z_mod.move_cup_z()

        assert recorded == [
            (578.45, -222.64, 556.32, 54.96, -180.0, 54.72),
            (338.57, -222.64, 556.32, 136.05, 179.95, 135.81),
            (338.57, -170.40, 556.32, 136.05, 179.95, 135.81),
        ]


def test_handle_scoop_icecream_runs_non_interactive() -> None:
    """Verify SCOOP_ICECREAM handler delegates to scoop_icecream(interactive=False)."""
    rclpy.init()
    node = MotionManagerNode()
    try:
        with patch.object(
            motion_manager_node,
            "scoop_icecream",
            return_value="스쿠핑 및 투하 완료",
        ) as mock_scoop:
            ok, code, msg = node._handle_scoop_icecream("")
            assert ok is True
            assert code == ERROR_NONE
            assert msg == "스쿠핑 및 투하 완료"
            mock_scoop.assert_called_once_with(interactive=False)

        with patch.object(
            motion_manager_node,
            "flatten_icecream",
            return_value="아이스크림 평탄화 완료",
        ) as mock_flatten:
            ok, code, msg = node._handle_flatten_icecream("")
            assert ok is True
            assert code == ERROR_NONE
            assert msg == "아이스크림 평탄화 완료"
            mock_flatten.assert_called_once_with()
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


def test_cup_diameter_hit_persistence_roundtrip(tmp_path, monkeypatch) -> None:
    """Verify cup diameter contact pose save, load, and clear use configured path."""
    hit_file = tmp_path / "cup_diameter_hit.json"
    monkeypatch.setenv("ICECREAM_DIAMETER_HIT_FILE", str(hit_file))

    assert pose_config_mod.load_cup_diameter_hit() is None
    saved = pose_config_mod.save_cup_diameter_hit(
        [352.16, -145.84, 306.45, 0.0, -180.0, 45.0],
        diameter=87.0,
        radius=43.5,
        cup_height_mm=88.45,
    )
    assert saved == hit_file
    loaded = pose_config_mod.load_cup_diameter_hit()
    assert loaded is not None
    assert loaded["hit_pos"] == [352.16, -145.84, 306.45, 0.0, -180.0, 45.0]
    assert loaded["diameter"] == 87.0
    assert loaded["radius"] == 43.5

    pose_config_mod.clear_cup_diameter_hit()
    assert pose_config_mod.load_cup_diameter_hit() is None


def test_calibrate_cup_diameter_saves_first_hit_pose(tmp_path, monkeypatch) -> None:
    """Verify calibrate_cup_diameter persists first_hit coordinates on contact."""
    hit_file = tmp_path / "cup_diameter_hit.json"
    monkeypatch.setenv("ICECREAM_DIAMETER_HIT_FILE", str(hit_file))

    fake_common = ModuleType("DR_common2")
    fake_common.posj = lambda *j: tuple(j)
    fake_common.posx = lambda *p: tuple(p)

    fake_dsr = ModuleType("DSR_ROBOT2")
    fake_dsr.DR_BASE = 0
    fake_dsr.movej = lambda *args, **kwargs: 0
    fake_dsr.movel = lambda *args, **kwargs: 0

    class _FakeSmoothCtrl:
        def __init__(self, node, sample_sleep=0.025) -> None:
            del node, sample_sleep

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read_baseline(self):
            return (0.0, 0.0, 0.0)

        def start_move(self, target, vel, acc):
            del target, vel, acc

        def monitor_motion(self, target):
            del target
            u = 0.70710678
            start_x = 273.0 + 165.0 * u
            start_y = -225.0 + 165.0 * u
            # Baseline samples between 2mm and 6mm, then 2 contact hits at L=111.95mm
            yield ([start_x - 2.5 * u, start_y - 2.5 * u, 306.45, 0.0, -180.0, 45.0], [0.1, 0.0, 0.0])
            yield ([start_x - 4.5 * u, start_y - 4.5 * u, 306.45, 0.0, -180.0, 45.0], [0.1, 0.0, 0.0])
            yield ([273.0 + 111.95 * u, -225.0 + 111.95 * u, 306.45, 0.0, -180.0, 45.0], [2.2, 0.2, 0.0])
            yield ([273.0 + 111.45 * u, -225.0 + 111.45 * u, 306.45, 0.0, -180.0, 45.0], [2.5, 0.3, 0.0])

        def stop(self):
            return [352.0, -146.0, 306.45, 0.0, -180.0, 45.0]

    rclpy.init()
    node = rclpy.create_node("test_cal_diam_hit")
    try:
        with patch.dict(sys.modules, {"DR_common2": fake_common, "DSR_ROBOT2": fake_dsr}):
            with patch.object(calibrate_cup_diameter_mod, "griper_grap"):
                with patch.object(calibrate_cup_diameter_mod, "SmoothController", _FakeSmoothCtrl):
                    with patch.object(calibrate_cup_diameter_mod.time, "sleep"):
                        res = calibrate_cup_diameter_mod.calibrate_cup_diameter(
                            node=node,
                            cup_height_mm=88.45,
                            allow_fallback=False,
                        )
    finally:
        node.destroy_node()
        rclpy.try_shutdown()

    assert res == (43.5, 87.0)
    saved = pose_config_mod.load_cup_diameter_hit()
    assert saved is not None
    assert round(saved["hit_pos"][0], 2) == 352.16
    assert round(saved["hit_pos"][1], 2) == -145.84
    assert saved["diameter"] == 87.0


def test_move_cup_hold_uses_saved_hit_minus_5mm(tmp_path, monkeypatch) -> None:
    """Verify move_cup_hold applies (-5mm, -5mm) to saved diameter contact XY and keeps height Z."""
    hit_file = tmp_path / "cup_diameter_hit.json"
    monkeypatch.setenv("ICECREAM_DIAMETER_HIT_FILE", str(hit_file))
    pose_config_mod.save_cup_diameter_hit(
        [352.16, -145.84, 306.45, 0.0, -180.0, 45.0],
        diameter=87.0,
        radius=43.5,
        cup_height_mm=88.45,
    )

    moved_targets: list[list[float]] = []
    fake_dsr = ModuleType("DSR_ROBOT2")
    fake_dsr.DR_BASE = 0
    fake_dsr.check_motion = lambda: 0
    current_pose = [367.47, 7.96, 423.09, -116.45, 179.97, -116.44]
    fake_dsr.get_current_posx = lambda ref=0: (list(current_pose), 0)

    def fake_move_axis_sequence(target, vel, acc, label=""):
        del vel, acc, label
        moved_targets.append(list(target))
        current_pose[:3] = target[:3]

    with patch.dict(sys.modules, {"DSR_ROBOT2": fake_dsr}):
        with patch.object(
            move_cup_hold_mod,
            "get_section_config",
            return_value={
                "ground_z": 0.0,
                "grip_depth": 10.0,
                "hit_offset_xy": [-5.0, -5.0],
            },
        ):
            with patch.object(
                move_cup_hold_mod,
                "get_motion_entry",
                return_value=(
                    [360.89, -145.12, 343.92, -124.86, 179.92, -163.43],
                    80.0,
                    80.0,
                ),
            ):
                with patch.object(
                    move_cup_hold_mod,
                    "move_axis_sequence",
                    side_effect=fake_move_axis_sequence,
                ):
                    result = move_cup_hold_mod.move_cup_hold(88.45, 87.0)

    assert round(result[0], 2) == 347.16
    assert round(result[1], 2) == -150.84
    assert round(result[2], 2) == 316.45
    assert moved_targets == [result]


def test_calibrate_cup_diameter_fails_without_contact() -> None:
    """Verify CALIBRATE_CUP_DIAMETER returns error when side contact is not detected."""
    rclpy.init()
    node = MotionManagerNode()
    try:
        node._latest_cup_height_z = 115.0
        with patch.object(
            motion_manager_node,
            "calibrate_cup_diameter",
            return_value=None,
        ) as mock_cal:
            ok, code, msg = node._handle_calibrate_cup_diameter("")
            assert ok is False
            assert code == ERROR_MOTION
            assert "감지되지" in msg
            assert node._latest_cup_diameter == 0.0
            mock_cal.assert_called_once_with(
                cup_height_mm=115.0,
                allow_fallback=False,
            )
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


def test_move_cup_hold_calculates_target_and_validates_arrival() -> None:
    """Verify move_cup_hold computes cup rim grip target from height and diameter."""
    moved_targets: list[list[float]] = []
    fake_dsr = ModuleType("DSR_ROBOT2")
    fake_dsr.DR_BASE = 0
    fake_dsr.check_motion = lambda: 0

    current_pose = [360.0, -145.0, 450.0, -124.86, 179.92, -163.43]
    fake_dsr.get_current_posx = lambda ref=0: (list(current_pose), 0)

    def fake_move_axis_sequence(target, vel, acc, label=""):
        del vel, acc, label
        moved_targets.append(list(target))
        current_pose[:3] = target[:3]

    with patch.dict(sys.modules, {"DSR_ROBOT2": fake_dsr}):
        with patch.object(move_cup_hold_mod, "CORNER_XY", (273.0, -225.0)):
            with patch.object(move_cup_hold_mod, "GROUND_Z", 0.0):
                with patch.object(move_cup_hold_mod, "GRIP_DEPTH", 10.0):
                    with patch.object(move_cup_hold_mod, "TCP_OFFSET", (-2.0, 35.0, 238.0)):
                        with patch.object(move_cup_hold_mod, "SAFE_Z", 410.0):
                            with patch.object(move_cup_hold_mod, "HEIGHT_RANGE", (60.0, 180.0)):
                                with patch.object(move_cup_hold_mod, "DIAMETER_RANGE", (40.0, 150.0)):
                                    with patch.object(
                                        move_cup_hold_mod,
                                        "get_section_config",
                                        return_value={},
                                    ):
                                        with patch.object(
                                            move_cup_hold_mod,
                                            "get_motion_entry",
                                            return_value=(
                                                [360.89, -145.12, 343.92, -124.86, 179.92, -163.43],
                                                80.0,
                                                80.0,
                                            ),
                                        ):
                                            with patch.object(
                                                move_cup_hold_mod,
                                                "load_cup_diameter_hit",
                                                return_value=None,
                                            ):
                                                with patch.object(
                                                    move_cup_hold_mod,
                                                    "move_axis_sequence",
                                                    side_effect=fake_move_axis_sequence,
                                                ):
                                                    result = move_cup_hold_mod.move_cup_hold(115.0, 90.0)

    # R=45 -> cup_x=318, cup_y=-180 -> grip=(363, -180, 105) + offset=(-2, 35, 238)
    assert result[:3] == [361.0, -145.0, 343.0]
    assert moved_targets == [result]


def test_move_cup_hold_works_with_default_measurement_settings() -> None:
    """Verify move_cup_hold runs with default cup-measurement settings without None errors."""
    fake_dsr = ModuleType("DSR_ROBOT2")
    fake_dsr.DR_BASE = 0
    fake_dsr.check_motion = lambda: 0
    current_pose = [367.0, 0.0, 424.5, -124.86, 179.92, -163.43]
    fake_dsr.get_current_posx = lambda ref=0: (list(current_pose), 0)

    def fake_move_axis_sequence(target, vel, acc, label=""):
        del vel, acc, label
        current_pose[:3] = target[:3]

    with patch.dict(sys.modules, {"DSR_ROBOT2": fake_dsr}):
        with patch.object(move_cup_hold_mod, "get_section_config", return_value={}):
            with patch.object(
                move_cup_hold_mod,
                "get_motion_entry",
                return_value=(
                    [360.89, -145.12, 343.92, -124.86, 179.92, -163.43],
                    80.0,
                    80.0,
                ),
            ):
                with patch.object(
                    move_cup_hold_mod,
                    "load_cup_diameter_hit",
                    return_value=None,
                ):
                    with patch.object(
                        move_cup_hold_mod,
                        "move_axis_sequence",
                        side_effect=fake_move_axis_sequence,
                    ):
                        result = move_cup_hold_mod.move_cup_hold(158.55, 90.0)

    expected_x = move_cup_hold_mod.CORNER_XY[0] + 90.0 + float(move_cup_hold_mod.TCP_OFFSET[0])
    expected_y = move_cup_hold_mod.CORNER_XY[1] + 45.0 + float(move_cup_hold_mod.TCP_OFFSET[1])
    expected_z = (
        move_cup_hold_mod.GROUND_Z
        + 158.55
        - move_cup_hold_mod.GRIP_DEPTH
        + float(move_cup_hold_mod.TCP_OFFSET[2])
    )
    assert result[:3] == [expected_x, expected_y, expected_z]


def test_handle_move_cup_hold_uses_target_or_latest_measurements() -> None:
    """Verify MotionManagerNode parses target or falls back to latest cup measurements."""
    rclpy.init()
    node = MotionManagerNode()
    try:
        node._latest_cup_height_z = 115.0
        node._latest_cup_diameter = 90.0
        with patch.object(motion_manager_node, "move_cup_hold") as mock_hold:
            ok, code, _msg = node._handle_move_cup_hold("")
            assert ok is True
            assert code == ERROR_NONE
            mock_hold.assert_called_once_with(cup_height=115.0, cup_diameter=90.0)

        with patch.object(motion_manager_node, "move_cup_hold") as mock_hold:
            ok, code, _msg = node._handle_move_cup_hold("120.5, 88.0")
            assert ok is True
            assert code == ERROR_NONE
            mock_hold.assert_called_once_with(cup_height=120.5, cup_diameter=88.0)

        ok, code, _msg = node._handle_move_cup_hold("120.5")
        assert ok is False
        assert code == ERROR_UNKNOWN_COMMAND
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


def test_calibrate_cup_z_stops_with_qstop_and_waits_for_ascent() -> None:
    """Verify calibration_cup_z uses stop_mode=1 on contact and waits for slow ascent."""
    stop_modes: list[int] = []
    current_z = 556.0
    motion_state = 0
    phase = "init"
    down_calls = 0

    class _FakeFuture:
        def __init__(self, success: bool = True) -> None:
            self._result = type("Res", (), {"success": success})()

        def done(self) -> bool:
            return True

        def result(self):
            return self._result

    class _FakeStopClient:
        def wait_for_service(self, timeout_sec: float = 3.0) -> bool:
            del timeout_sec
            return True

        def call_async(self, request):
            nonlocal motion_state, phase
            stop_modes.append(int(request.stop_mode))
            motion_state = 0
            phase = "stopped"
            return _FakeFuture(True)

    class _FakeNode:
        def create_client(self, srv_type, srv_name):
            del srv_type, srv_name
            return _FakeStopClient()

        def destroy_client(self, client) -> None:
            del client

    class _FakeRobot:
        DR_BASE = 0
        DR_MV_MOD_ABS = 0

        def check_motion(self) -> int:
            nonlocal down_calls, motion_state, current_z
            if phase == "descending":
                down_calls += 1
                motion_state = 1
                current_z = max(350.0, current_z - 1.0)
            elif phase == "ascending":
                down_calls += 1
                if down_calls < 3:
                    motion_state = 1
                else:
                    current_z = 556.0
                    motion_state = 0
            return motion_state

        def get_robot_state(self) -> int:
            return 1

        def get_current_posx(self, ref=0):
            del ref
            return ([338.57, -170.40, current_z, 136.05, 179.95, 135.81], 0)

        def get_tool_force(self, ref=0):
            del ref
            fz = 5.0 if phase == "descending" and current_z <= 355.0 else 0.0
            return [0.0, 0.0, fz, 0.0, 0.0, 0.0]

        def amovel(self, pos, vel=0.0, acc=0.0, ref=0, mod=0, radius=0.0):
            del pos, vel, acc, ref, mod, radius
            nonlocal phase, motion_state, down_calls
            if phase == "init":
                phase = "descending"
                motion_state = 1
            else:
                phase = "ascending"
                down_calls = 0
                motion_state = 1
            return 0

    fake_common = ModuleType("DR_common2")
    fake_common.posx = lambda coords: list(coords)

    with patch.dict(sys.modules, {"DR_common2": fake_common}):
        with patch.object(calibrate_cup_z_mod, "posx", lambda coords: list(coords)):
            with patch.object(calibrate_cup_z_mod.rclpy, "spin_until_future_complete"):
                with patch.object(calibrate_cup_z_mod.time, "sleep"):
                    with patch.object(
                        calibrate_cup_z_mod,
                        "_load_calibration_params",
                        return_value={
                            "gripper_mass_kg": 1.46,
                            "tip_offset_z": -238.0,
                            "ground_z": 0.0,
                            "min_z": 30.0,
                            "start_clear_mm": 8.0,
                            "down_speed": 20.0,
                            "down_acc": 5.0,
                            "up_speed": 100.0,
                            "up_acc": 15.0,
                            "force_limit": 2.0,
                            "start_abort_n": 4.0,
                            "max_seconds": 180.0,
                            "check_interval": 0.02,
                        },
                    ):
                        height = calibrate_cup_z_mod.calibration_cup_z(
                            robot=_FakeRobot(),
                            node=_FakeNode(),
                        )

    assert stop_modes == [1]
    assert height == 96.0


def test_ensure_default_tcp_resets_custom_tcp_and_registers_if_needed() -> None:
    """Verify ensure_default_tcp switches MANUAL->set_tcp/add_tcp->AUTONOMOUS when needed."""
    state = {"tcp": "tcptest", "mode": 1, "registered": set()}
    events: list[tuple[str, object]] = []

    fake_dsr = ModuleType("DSR_ROBOT2")
    fake_dsr.ROBOT_MODE_MANUAL = 0
    fake_dsr.ROBOT_MODE_AUTONOMOUS = 1
    fake_dsr.get_tcp = lambda: state["tcp"]
    fake_dsr.get_robot_mode = lambda: state["mode"]

    def fake_set_robot_mode(mode: int) -> int:
        events.append(("set_mode", mode))
        state["mode"] = mode
        return 0

    def fake_set_tcp(name: str) -> int:
        events.append(("set_tcp", name))
        if name not in state["registered"]:
            return -1
        state["tcp"] = name
        return 0

    def fake_add_tcp(name: str, pos: list[float]) -> int:
        events.append(("add_tcp", (name, list(pos))))
        state["registered"].add(name)
        return 0

    fake_dsr.set_robot_mode = fake_set_robot_mode
    fake_dsr.set_tcp = fake_set_tcp
    fake_dsr.add_tcp = fake_add_tcp

    with patch.dict(sys.modules, {"DSR_ROBOT2": fake_dsr}):
        with patch.object(motion_utils, "get_section_config", return_value={}):
            restored = motion_utils.ensure_default_tcp()
            assert restored == "flange_default"
            assert state["tcp"] == "flange_default"
            assert state["mode"] == 1
            assert events == [
                ("set_mode", 0),
                ("set_tcp", "flange_default"),
                ("add_tcp", ("flange_default", [0.0, 0.0, 0.0, 0.0, 0.0, 0.0])),
                ("set_tcp", "flange_default"),
                ("set_mode", 1),
            ]

            # 이미 기본 TCP면 모드 전환 없이 즉시 반환
            events.clear()
            assert motion_utils.ensure_default_tcp() == "flange_default"
            assert events == []


def test_move_home_calls_ensure_default_tcp() -> None:
    """Verify move_home restores default TCP before movel homing and opens gripper."""
    calls: list[tuple] = []
    fake_dsr = ModuleType("DSR_ROBOT2")
    fake_dsr.DR_BASE = 0
    fake_dsr.DR_MV_MOD_ABS = 0
    fake_dsr.posx = lambda *coords: tuple(coords)

    def fake_movel(pos, vel=0.0, acc=0.0, ref=0, mod=0):
        calls.append(("movel", pos, vel, acc, ref, mod))
        return 0

    fake_dsr.movel = fake_movel

    home_pose = [367.47, 7.96, 423.09, 96.96, 179.96, 96.72]
    with patch.dict(sys.modules, {"DSR_ROBOT2": fake_dsr}):
        with patch.object(
            move_home_mod,
            "get_motion_entry",
            return_value=(home_pose, 70.0, 70.0),
        ):
            with patch.object(
                move_home_mod,
                "ensure_default_tcp",
                side_effect=lambda: calls.append(("tcp",)),
            ):
                with patch.object(
                    move_home_mod,
                    "grip_release",
                    side_effect=lambda: calls.append(("release",)),
                ):
                    move_home_mod.move_home()

    assert calls == [
        ("tcp",),
        ("movel", tuple(home_pose), 70.0, 70.0, 0, 0),
        ("release",),
    ]


def test_move_blending_builds_posb_segments_with_zero_last_radius() -> None:
    """Verify motion_utils.move_blending converts waypoints to posb and forces last radius=0."""
    captured: list[tuple] = []

    class _FakePosb:
        def __init__(self, seg_type, posx1, posx2=None, radius=0.0) -> None:
            self._seg_type = seg_type
            self._posx1 = posx1
            self._posx2 = posx2
            self._radius = radius

    fake_common = ModuleType("DR_common2")
    fake_common.posb = _FakePosb
    fake_common.posx = lambda *coords: tuple(coords)

    fake_dsr = ModuleType("DSR_ROBOT2")
    fake_dsr.DR_BASE = 0
    fake_dsr.DR_LINE = 0
    fake_dsr.DR_MV_MOD_ABS = 0

    def fake_dsr_amoveb(seg_list, vel=0.0, acc=0.0, ref=0, mod=0, time=0.0):
        captured.append((seg_list, vel, acc, ref, mod, time))
        return 0

    fake_dsr.amoveb = fake_dsr_amoveb

    p1 = [400.0, -150.0, 450.0, 0.0, 180.0, 0.0]
    p2 = [350.0, -170.0, 450.0, 0.0, 180.0, 0.0]
    p3 = [350.0, -170.0, 320.0, 0.0, 180.0, 0.0]

    with patch.dict(sys.modules, {"DR_common2": fake_common, "DSR_ROBOT2": fake_dsr}):
        with patch.object(motion_utils, "wait_for_motion") as mock_wait:
            motion_utils.move_blending(
                [(p1, 25.0), p2, (p3, 15.0)],
                vel=80.0,
                acc=80.0,
                default_radius=20.0,
            )

    mock_wait.assert_called_once()
    assert len(captured) == 1
    seg_list, vel, acc, ref, mod, time_sec = captured[0]
    assert (vel, acc, ref, mod, time_sec) == (80.0, 80.0, 0, 0, 0.0)
    assert [s._radius for s in seg_list] == [25.0, 20.0, 0.0]
    assert [s._posx1 for s in seg_list] == [tuple(p1), tuple(p2), tuple(p3)]


def test_move_to_plate_uses_move_blending_with_safe_radii() -> None:
    """Verify move_to_plate routes X->Y->Z waypoints through move_blending with clamped radii."""
    blended_calls: list[tuple] = []
    fake_dsr = ModuleType("DSR_ROBOT2")
    fake_dsr.DR_BASE = 0
    fake_dsr.DR_MV_MOD_ABS = 0
    fake_dsr.amovel = lambda *args, **kwargs: 0
    fake_dsr.posx = lambda *coords: tuple(coords)
    fake_dsr.get_current_posx = lambda ref=0: (
        [338.57, -170.40, 556.32, 136.05, 179.95, 135.81],
        0,
    )

    def fake_move_blending(waypoints, vel=0.0, acc=0.0, label=""):
        blended_calls.append((waypoints, vel, acc, label))

    target = [573.59, -135.38, 249.19, -121.31, 179.81, -121.34]
    with patch.dict(sys.modules, {"DSR_ROBOT2": fake_dsr}):
        with patch.object(motion_utils, "get_motion_via", return_value=None):
            with patch.object(
                motion_utils,
                "get_motion_entry",
                return_value=(target, 80.0, 80.0),
            ):
                with patch.object(
                    motion_utils,
                    "get_section_config",
                    return_value={"blend_radius": 20.0},
                ):
                    with patch.object(
                        motion_utils,
                        "move_blending",
                        side_effect=fake_move_blending,
                    ):
                        move_to_plate_mod.move_to_plate()

    assert len(blended_calls) == 1
    waypoints, vel, acc, label = blended_calls[0]
    assert (vel, acc, label) == (80.0, 80.0, "측정판")
    # ΔX=235.02, ΔY=35.02, ΔZ=307.13 -> 두 번째 코너는 ΔY*0.4 = 14.01로 클램프, 마지막은 0.0
    assert [wp[0][:3] for wp in waypoints] == [
        [573.59, -170.40, 556.32],
        [573.59, -135.38, 556.32],
        [573.59, -135.38, 249.19],
    ]
    assert [wp[1] for wp in waypoints] == [14.01, 14.01, 0.0]


def test_move_axis_sequence_uses_move_blending_20mm() -> None:
    """Verify move_axis_sequence delegates waypoints to move_blending with 20mm radius when enabled."""
    calls: list[tuple] = []
    fake_dsr = ModuleType("DSR_ROBOT2")
    fake_dsr.DR_BASE = 0
    fake_dsr.DR_MV_MOD_ABS = 0
    fake_dsr.amovel = lambda *args, **kwargs: 0
    fake_dsr.posx = lambda *coords: tuple(coords)
    fake_dsr.get_current_posx = lambda ref=0: (
        [200.0, 0.0, 450.0, 0.0, 180.0, 0.0],
        0,
    )

    def fake_move_blending(waypoints, vel=0.0, acc=0.0, label=""):
        calls.append((waypoints, vel, acc, label))

    target = [360.0, -180.0, 340.0, -124.86, 179.92, -163.43]
    with patch.dict(sys.modules, {"DSR_ROBOT2": fake_dsr}):
        with patch.object(motion_utils, "move_blending", side_effect=fake_move_blending):
            motion_utils.move_axis_sequence(
                target,
                vel=80.0,
                acc=80.0,
                label="테스트",
                use_blending=True,
            )

    assert len(calls) == 1
    waypoints, vel, acc, label = calls[0]
    assert (vel, acc, label) == (80.0, 80.0, "테스트")
    assert [wp[0][:3] for wp in waypoints] == [
        [360.0, 0.0, 450.0],
        [360.0, -180.0, 450.0],
        [360.0, -180.0, 340.0],
    ]
    assert [wp[1] for wp in waypoints] == [20.0, 20.0, 0.0]


def test_move_axis_sequence_defaults_to_sequential_amovel() -> None:
    """Verify move_axis_sequence uses sequential amovel by default (e.g. move_cup_hold)."""
    amovel_calls: list[tuple] = []
    fake_dsr = ModuleType("DSR_ROBOT2")
    fake_dsr.DR_BASE = 0
    fake_dsr.DR_MV_MOD_ABS = 0
    fake_dsr.posx = lambda *coords: tuple(coords)
    fake_dsr.get_current_posx = lambda ref=0: (
        [367.47, 7.96, 423.09, -116.45, 179.97, -116.44],
        0,
    )

    def fake_amovel(pos, vel=0.0, acc=0.0, ref=0, mod=0):
        amovel_calls.append((pos, vel, acc, ref, mod))
        return 0

    fake_dsr.amovel = fake_amovel

    target = [360.0, -181.5, 316.45, -124.86, 179.92, -163.43]
    with patch.dict(sys.modules, {"DSR_ROBOT2": fake_dsr}):
        with patch.object(motion_utils, "wait_for_motion") as mock_wait:
            with patch.object(
                motion_utils,
                "move_blending",
                side_effect=AssertionError("move_blending should not be called by default"),
            ):
                motion_utils.move_axis_sequence(
                    target,
                    vel=80.0,
                    acc=80.0,
                    label="컵 크기 기반 홀드 위치",
                )

    assert len(amovel_calls) == 3
    assert mock_wait.call_count == 3
    assert [c[0][:3] for c in amovel_calls] == [
        (360.0, 7.96, 423.09),
        (360.0, -181.5, 423.09),
        (360.0, -181.5, 316.45),
    ]


def test_move_cup_z_uses_sequential_movel_z_then_xy() -> None:
    """Verify move_cup_z calls movel for Z first and then target XY regardless of start Z."""
    for start_z in (284.72, 628.0):
        recorded: list[tuple[float, ...]] = []
        fake_dsr = ModuleType("DSR_ROBOT2")
        fake_dsr.DR_BASE = 0
        fake_dsr.DR_MV_MOD_ABS = 0
        fake_dsr.posx = lambda *coords: tuple(coords)
        fake_dsr.get_current_posx = lambda ref=0: (
            [578.45, -222.64, start_z, 54.96, -180.0, 54.72],
            0,
        )

        def fake_movel(pos, vel=0.0, acc=0.0, ref=0, mod=0):
            del vel, acc, ref, mod
            recorded.append(pos)
            return 0

        fake_dsr.movel = fake_movel

        target = [338.57, -170.40, 556.32, 136.05, 179.95, 135.81]
        with patch.dict(sys.modules, {"DSR_ROBOT2": fake_dsr}):
            with patch.object(move_cup_z_mod, "get_motion_via", return_value=None):
                with patch.object(
                    move_cup_z_mod,
                    "get_motion_entry",
                    return_value=(target, 80.0, 80.0),
                ):
                    move_cup_z_mod.move_cup_z()

        assert recorded == [
            (578.45, -222.64, 556.32, 54.96, -180.0, 54.72),
            (338.57, -222.64, 556.32, 136.05, 179.95, 135.81),
            (338.57, -170.40, 556.32, 136.05, 179.95, 135.81),
        ]


def test_handle_scoop_icecream_runs_non_interactive() -> None:
    """Verify SCOOP_ICECREAM handler delegates to scoop_icecream(interactive=False)."""
    rclpy.init()
    node = MotionManagerNode()
    try:
        with patch.object(
            motion_manager_node,
            "scoop_icecream",
            return_value="스쿠핑 및 투하 완료",
        ) as mock_scoop:
            ok, code, msg = node._handle_scoop_icecream("")
            assert ok is True
            assert code == ERROR_NONE
            assert msg == "스쿠핑 및 투하 완료"
            mock_scoop.assert_called_once_with(interactive=False)

        with patch.object(
            motion_manager_node,
            "flatten_icecream",
            return_value="아이스크림 평탄화 완료",
        ) as mock_flatten:
            ok, code, msg = node._handle_flatten_icecream("")
            assert ok is True
            assert code == ERROR_NONE
            assert msg == "아이스크림 평탄화 완료"
            mock_flatten.assert_called_once_with()
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


def test_cup_diameter_hit_persistence_roundtrip(tmp_path, monkeypatch) -> None:
    """Verify cup diameter contact pose save, load, and clear use configured path."""
    hit_file = tmp_path / "cup_diameter_hit.json"
    monkeypatch.setenv("ICECREAM_DIAMETER_HIT_FILE", str(hit_file))

    assert pose_config_mod.load_cup_diameter_hit() is None
    saved = pose_config_mod.save_cup_diameter_hit(
        [352.16, -145.84, 306.45, 0.0, -180.0, 45.0],
        diameter=87.0,
        radius=43.5,
        cup_height_mm=88.45,
    )
    assert saved == hit_file
    loaded = pose_config_mod.load_cup_diameter_hit()
    assert loaded is not None
    assert loaded["hit_pos"] == [352.16, -145.84, 306.45, 0.0, -180.0, 45.0]
    assert loaded["diameter"] == 87.0
    assert loaded["radius"] == 43.5

    pose_config_mod.clear_cup_diameter_hit()
    assert pose_config_mod.load_cup_diameter_hit() is None


def test_calibrate_cup_diameter_saves_first_hit_pose(tmp_path, monkeypatch) -> None:
    """Verify calibrate_cup_diameter persists first_hit coordinates on contact."""
    hit_file = tmp_path / "cup_diameter_hit.json"
    monkeypatch.setenv("ICECREAM_DIAMETER_HIT_FILE", str(hit_file))

    fake_common = ModuleType("DR_common2")
    fake_common.posj = lambda *j: tuple(j)
    fake_common.posx = lambda *p: tuple(p)

    fake_dsr = ModuleType("DSR_ROBOT2")
    fake_dsr.DR_BASE = 0
    fake_dsr.movej = lambda *args, **kwargs: 0
    fake_dsr.movel = lambda *args, **kwargs: 0

    class _FakeSmoothCtrl:
        def __init__(self, node, sample_sleep=0.025) -> None:
            del node, sample_sleep

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read_baseline(self):
            return (0.0, 0.0, 0.0)

        def start_move(self, target, vel, acc):
            del target, vel, acc

        def monitor_motion(self, target):
            del target
            u = 0.70710678
            start_x = 273.0 + 165.0 * u
            start_y = -225.0 + 165.0 * u
            # Baseline samples between 2mm and 6mm, then 2 contact hits at L=111.95mm
            yield ([start_x - 2.5 * u, start_y - 2.5 * u, 306.45, 0.0, -180.0, 45.0], [0.1, 0.0, 0.0])
            yield ([start_x - 4.5 * u, start_y - 4.5 * u, 306.45, 0.0, -180.0, 45.0], [0.1, 0.0, 0.0])
            yield ([273.0 + 111.95 * u, -225.0 + 111.95 * u, 306.45, 0.0, -180.0, 45.0], [2.2, 0.2, 0.0])
            yield ([273.0 + 111.45 * u, -225.0 + 111.45 * u, 306.45, 0.0, -180.0, 45.0], [2.5, 0.3, 0.0])

        def stop(self):
            return [352.0, -146.0, 306.45, 0.0, -180.0, 45.0]

    rclpy.init()
    node = rclpy.create_node("test_cal_diam_hit")
    try:
        with patch.dict(sys.modules, {"DR_common2": fake_common, "DSR_ROBOT2": fake_dsr}):
            with patch.object(calibrate_cup_diameter_mod, "griper_grap"):
                with patch.object(calibrate_cup_diameter_mod, "SmoothController", _FakeSmoothCtrl):
                    with patch.object(calibrate_cup_diameter_mod.time, "sleep"):
                        res = calibrate_cup_diameter_mod.calibrate_cup_diameter(
                            node=node,
                            cup_height_mm=88.45,
                            allow_fallback=False,
                        )
    finally:
        node.destroy_node()
        rclpy.try_shutdown()

    assert res == (43.5, 87.0)
    saved = pose_config_mod.load_cup_diameter_hit()
    assert saved is not None
    assert round(saved["hit_pos"][0], 2) == 352.16
    assert round(saved["hit_pos"][1], 2) == -145.84
    assert saved["diameter"] == 87.0


def test_move_cup_hold_uses_saved_hit_minus_5mm(tmp_path, monkeypatch) -> None:
    """Verify move_cup_hold applies (-5mm, -5mm) to saved diameter contact XY and keeps height Z."""
    hit_file = tmp_path / "cup_diameter_hit.json"
    monkeypatch.setenv("ICECREAM_DIAMETER_HIT_FILE", str(hit_file))
    pose_config_mod.save_cup_diameter_hit(
        [352.16, -145.84, 306.45, 0.0, -180.0, 45.0],
        diameter=87.0,
        radius=43.5,
        cup_height_mm=88.45,
    )

    moved_targets: list[list[float]] = []
    fake_dsr = ModuleType("DSR_ROBOT2")
    fake_dsr.DR_BASE = 0
    fake_dsr.check_motion = lambda: 0
    current_pose = [367.47, 7.96, 423.09, -116.45, 179.97, -116.44]
    fake_dsr.get_current_posx = lambda ref=0: (list(current_pose), 0)

    def fake_move_axis_sequence(target, vel, acc, label=""):
        del vel, acc, label
        moved_targets.append(list(target))
        current_pose[:3] = target[:3]

    with patch.dict(sys.modules, {"DSR_ROBOT2": fake_dsr}):
        with patch.object(
            move_cup_hold_mod,
            "get_section_config",
            return_value={
                "ground_z": 0.0,
                "grip_depth": 10.0,
                "hit_offset_xy": [-5.0, -5.0],
            },
        ):
            with patch.object(
                move_cup_hold_mod,
                "get_motion_entry",
                return_value=(
                    [360.89, -145.12, 343.92, -124.86, 179.92, -163.43],
                    80.0,
                    80.0,
                ),
            ):
                with patch.object(
                    move_cup_hold_mod,
                    "move_axis_sequence",
                    side_effect=fake_move_axis_sequence,
                ):
                    result = move_cup_hold_mod.move_cup_hold(88.45, 87.0)

    assert round(result[0], 2) == 347.16
    assert round(result[1], 2) == -150.84
    assert round(result[2], 2) == 316.45
    assert moved_targets == [result]


def test_handle_release_scoop_delegates_to_return_spoon() -> None:
    """Verify RELEASE_SCOOP and RETURN_SPOON handlers call return_spoon()."""
    rclpy.init()
    node = MotionManagerNode()
    try:
        assert "RELEASE_SCOOP" in node._task_handlers
        assert "RETURN_SPOON" in node._task_handlers
        assert "RELEASE_SCOOP" not in motion_manager_node.PLANNED_COMMANDS

        with patch.object(
            motion_manager_node,
            "return_spoon",
            return_value="스쿱 거치 복귀 완료",
        ) as mock_return:
            ok, code, msg = node._handle_release_scoop("")
            assert ok is True
            assert code == ERROR_NONE
            assert msg == "스쿱 거치 복귀 완료"
            mock_return.assert_called_once_with()
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


def test_return_spoon_executes_approach_place_release_and_lift() -> None:
    """Verify return_spoon runs moveb approach, movel place, DO2 release, and clearance lift."""
    current_pose = [313.03, -119.04, 240.13, 87.78, -90.0, 180.0]
    moveb_calls: list[dict] = []
    movel_calls: list[dict] = []
    do_calls: list[tuple[int, int]] = []
    mode_calls: list[int] = []

    fake_dsr = ModuleType("DSR_ROBOT2")
    fake_dsr.DR_BASE = 0
    fake_dsr.DR_LINE = 1
    fake_dsr.DR_MV_MOD_ABS = 0
    fake_dsr.ROBOT_MODE_AUTONOMOUS = 1
    fake_dsr.check_motion = lambda: 0
    fake_dsr.get_robot_state = lambda: 1
    fake_dsr.posx = lambda coords: list(coords)
    fake_dsr.posb = lambda seg_type, pose, radius=0.0: (seg_type, list(pose), radius)
    fake_dsr.get_current_posx = lambda ref=0: (list(current_pose), 0)

    def fake_set_robot_mode(mode: int) -> int:
        mode_calls.append(mode)
        return 0

    def fake_moveb(path, vel, acc, ref=0, mod=0) -> int:
        moveb_calls.append({"path": list(path), "vel": vel, "acc": acc, "ref": ref, "mod": mod})
        current_pose[:] = list(path[-1][1])
        return 0

    def fake_movel(pose, vel, acc, ref=0, mod=0, radius=0.0) -> int:
        movel_calls.append(
            {"pose": list(pose), "vel": vel, "acc": acc, "ref": ref, "mod": mod, "radius": radius}
        )
        current_pose[:] = list(pose)
        return 0

    def fake_set_do(channel: int, value: int) -> int:
        do_calls.append((channel, value))
        return 0

    fake_dsr.set_robot_mode = fake_set_robot_mode
    fake_dsr.moveb = fake_moveb
    fake_dsr.movel = fake_movel
    fake_dsr.set_digital_output = fake_set_do

    rclpy.init()
    node = rclpy.create_node("test_return_spoon")
    try:
        with patch.dict(sys.modules, {"DSR_ROBOT2": fake_dsr}):
            with patch.object(return_spoon_mod, "ensure_default_tcp") as mock_tcp:
                with patch.object(return_spoon_mod.time, "sleep"):
                    result = return_spoon_mod.return_spoon(node=node)
    finally:
        node.destroy_node()
        rclpy.try_shutdown()

    expected_safe_z = return_spoon_mod.TARGET[2] + return_spoon_mod.CLEARANCE
    assert "스쿱 거치 복귀 완료" in result
    mock_tcp.assert_called_once_with()
    assert mode_calls == [fake_dsr.ROBOT_MODE_AUTONOMOUS]
    assert len(moveb_calls) == 1
    assert moveb_calls[0]["path"][0][1][2] == expected_safe_z
    assert moveb_calls[0]["path"][1][1] == [
        return_spoon_mod.TARGET[0],
        return_spoon_mod.TARGET[1],
        expected_safe_z,
        return_spoon_mod.TARGET[3],
        return_spoon_mod.TARGET[4],
        return_spoon_mod.TARGET[5],
    ]
    assert len(movel_calls) == 2
    assert movel_calls[0]["pose"] == return_spoon_mod.TARGET
    assert movel_calls[0]["vel"] == return_spoon_mod.DOWN_SPEED
    assert movel_calls[1]["pose"][2] == expected_safe_z
    assert movel_calls[1]["vel"] == return_spoon_mod.UP_SPEED
    assert do_calls == [(1, 0), (2, 1), (2, 0)]

