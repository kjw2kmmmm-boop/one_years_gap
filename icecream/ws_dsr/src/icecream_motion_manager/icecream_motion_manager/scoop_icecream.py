"""Doosan M0609 / ROS 2 Jazzy: force-20N push -> TCP vertical lift -> move_periodic -> J6 flip.

Sequence: J_READY -> TCP 'tcptest' -> B=210/C=0 entry at Z=220mm -> compliance on
-> descend continuously with amovel, detect force during motion and stop
-> at >=10N for 2 consecutive force samples stop motion -> push -Y until 20N (max 200mm)
-> rotate B=180 at fixed TCP XYZ -> raise TCP Z with X/Y fixed while changing B=180 to B=130 -> periodic Z shake
-> move linearly (movel) to (313.03, -119.04, 240.13, 87.78, -90.0, 180.0)
-> flip spoon 180 deg using J6-only movej -> periodic Z shake again -> return upright via movej.
"""
#마지막 조인트 값을 조정하여 사용 

import math
import time
import statistics

import rclpy
import DR_init

from dsr_msgs2.srv import MoveStop

from icecream_motion_manager.motion_utils import ensure_default_tcp

ROBOT_ID = "dsr01"
ROBOT_MODEL = "m0609"


def scoop_icecream(node=None, *, interactive: bool = False) -> str:
    """순응제어·힘 감지로 아이스크림을 스쿠핑한 뒤 지정 위치로 투하한다."""
    if node is None:
        node = DR_init.__dsr__node
    if node is None:
        raise RuntimeError("DR_init.__dsr__node가 초기화되지 않았습니다.")

    # Import AFTER assigning DR_init.__dsr__node.
    from DSR_ROBOT2 import (
        ROBOT_MODE_MANUAL,
        ROBOT_MODE_AUTONOMOUS,
        set_robot_mode,
        set_tcp,
        get_tcp,
        set_ref_coord,
        movej,
        movel,
        move_periodic,
        amovel,
        check_motion,
        posj,
        posx,
        get_current_posx,
        get_current_posj,
        task_compliance_ctrl,
        release_compliance_ctrl,
        get_tool_force,
        DR_BASE,
    )

    # ==========================================================
    # Motion settings
    # ==========================================================
    VEL_J_READY = 25             # 기존 J_READY 관절 이동 속도는 유지 (주변 간섭 우려)
    ACC_J_READY = 25
    VEL_APPROACH = 30             # 초기 TCP 좌표 진입 속도만 상향
    ACC_APPROACH = 30
    VEL_DESCENT = 25
    ACC_DESCENT = 25
    VEL_SCOOP = 15
    ACC_SCOOP = 15
    VEL_ROTATE = 8
    ACC_ROTATE = 8
    SHAKE_PERIOD_SEC = 0.8       # Z축 왕복 한 주기 (초)
    SHAKE_ATIME_SEC = 0.2        # 주기 모션 가속/감속 시간 (초)
    SHAKE_REPEAT = 10            # 기존 두 번째 털기 반복 횟수

    # 첫 번째 털기(B=130°)만 별도 저속 설정: ±30mm/0.8초의 고속 요구 완화
    SHAKE1_Z_MM = 10.0            # 첫 번째 털기 진폭 ±10mm
    SHAKE1_PERIOD_SEC = 1.5       # 첫 번째 털기 1회 주기 (초)
    SHAKE1_ATIME_SEC = 0.3        # 첫 번째 털기 가감속 시간 (초)
    SHAKE1_REPEAT = 10            # 첫 번째 털기 10회
    VEL_TCP_LIFT = [20.0, 12.0]  # 스푼 끝 상승 [선속도 mm/s, 각속도 deg/s]
    ACC_TCP_LIFT = [30.0, 20.0]  # 스푼 끝 상승 [선가속도 mm/s², 각가속도 deg/s²]
    VEL_TRANSFER = 50            # 4-1: 지정 TCP 자세 이동 속도 (mm/s)
    ACC_TRANSFER = 25            # 4-1: 지정 TCP 자세 이동 가속도 (mm/s^2)
    VEL_DROP_FLIP = 65           # 4-2: 스푼(J6) 180° 뒤집기 속도 (deg/s)
    ACC_DROP_FLIP = 35           # 4-2: 스푼(J6) 180° 뒤집기 가속도 (deg/s^2)
    VEL_DROP_RETURN = 20         # 4-3: 스푼(J6) 원위치 복귀 속도 (deg/s)
    ACC_DROP_RETURN = 20         # 4-3: 스푼(J6) 원위치 복귀 가속도 (deg/s^2)

    TCP_NAME = "tcptest"         # ALREADY registered on the controller
    TCP_Z_OFFSET = 248.0         # for geometric safety estimate only

    COMPLIANCE_STIFFNESS = [3000.0, 3000.0, 1500.0, 200.0, 200.0, 200.0]
    FORCE_THRESHOLD_N = 10.0     # |Fz - baseline_Fz|
    FORCE_SAMPLE_INTERVAL_S = 0.02  # 연속 하강 중 힘 감시 주기(요청 간 지연은 별도)
    DESCENT_TIMEOUT_S = 30.0        # 하강 감시 시간 초과
    MAX_DESCENT_MM = 150.0       # distance from start of descent
    STOP_SERVICE_NAMES = (
        f"/{ROBOT_ID}/dsr_controller2/motion/move_stop",
        f"/{ROBOT_ID}/motion/move_stop",
    )

    MIN_DESCEND_Z = 65.0        # absolute DR_BASE Z lower bound
    FLOOR_MARGIN = 20.0
    FLANGE_MIN_Z = 45.0
    FLOOR_Z = 0.0

    J_READY = [0.0, 0.0, 90.0, 0.0, 90.0, 0.0]
    START_X = 580.26
    START_Y = 187.63
    START_Z = 220.0              # 초기 좌표 이동 시 올라갈 Z 높이 (mm)
    LIFT_TARGET_Z = START_Z       # 상승 후 스푼 끝 TCP 목표 Z (DR_BASE, mm)

    # ==========================================================
    # Drop (투하) 설정
    # ==========================================================
    PLACE_X = 313.03             # 목적지 TCP X (DR_BASE, mm)
    PLACE_Y = -119.04            # 목적지 TCP Y (DR_BASE, mm)
    PLACE_Z = 240.13             # 목적지 TCP Z (DR_BASE, mm)
    PLACE_A = 87.78              # 목적지 TCP A (degree)
    PLACE_B = -90.00             # 목적지 TCP B (degree)
    PLACE_C = 180.0              # 목적지 TCP C (degree)
    DROP_HOLD_SEC = 1.5          # 뒤집힌 상태로 내용물이 떨어지길 기다리는 시간 (초)
    RETURN_UPRIGHT_AFTER_DROP = True  # 투하 후 스푼을 다시 원래 각도로 복귀할지 여부

    SCOOP_RX = -90.0
    RY_ENTRY = 210.0             # 진입 및 긁기 각도
    RY_MID = 180.0               # 20N 밀기 후 스푼 끝을 고정해 정렬할 B 각도
    SHAKE_Z_MM = 30.0             # 2차 털기: DR_BASE Z축 방향 ±30mm 진폭
    RY_LIFT = 130.0              # Z 상승과 동시에 변경할 B 각도
    SCOOP_RZ = 0.0
    SCOOP_DIST_Y = 250.0       # -Y 방향 밀기 최대 거리 (mm)
    PUSH_FORCE_THRESHOLD_N = 8.0  # 밀기 시작 직전 Fy 기준값 대비 변화량 (N)
    PUSH_SAMPLE_INTERVAL_S = 0.02  # 힘 조회 사이 추가 대기 시간 (초)
    PUSH_TIMEOUT_S = 30.0          # 연속 밀기 감시 제한 시간 (초)

    compliance_active = False

    def checked(result, name):
        """DSR_ROBOT2 Python motion/system wrappers: success -> 0."""
        if result != 0:
            raise RuntimeError(f"{name} 실패: 반환값={result!r}")

    def read_tcp_pose():
        pose, _ = get_current_posx(DR_BASE)
        if pose is None or not isinstance(pose, (list, tuple)) or len(pose) != 6:
            raise RuntimeError(f"TCP 좌표 조회 실패: {pose!r}")
        values = [float(v) for v in pose]
        if not all(math.isfinite(v) for v in values):
            raise RuntimeError("TCP 좌표에 NaN/Inf가 포함되어 있습니다.")
        return values

    def read_joint_pose():
        joints = get_current_posj()
        if (
            isinstance(joints, tuple)
            and len(joints) == 2
            and isinstance(joints[0], (list, tuple))
        ):
            joints = joints[0]
        if joints is None or not isinstance(joints, (list, tuple)) or len(joints) != 6:
            raise RuntimeError(f"Joint 각도 조회 실패: {joints!r}")
        values = [float(v) for v in joints]
        if not all(math.isfinite(v) for v in values):
            raise RuntimeError("Joint 각도에 NaN/Inf가 포함되어 있습니다.")
        return values

    def read_tool_force_z():
        force = get_tool_force(DR_BASE)
        if force is None or not isinstance(force, (list, tuple)) or len(force) != 6:
            raise RuntimeError(f"힘 데이터 조회 실패: {force!r}")
        values = [float(v) for v in force]
        if not all(math.isfinite(v) for v in values):
            raise RuntimeError("힘 데이터에 NaN/Inf가 포함되어 있습니다.")
        return values[2]

    def read_tool_force_y():
        """DR_BASE 기준 Y축 외력 Fy (N). -Y 방향 밀기의 반력 감시용."""
        force = get_tool_force(DR_BASE)
        if force is None or not isinstance(force, (list, tuple)) or len(force) != 6:
            raise RuntimeError(f"밀기 중 힘 데이터 조회 실패: {force!r}")
        values = [float(v) for v in force]
        if not all(math.isfinite(v) for v in values):
            raise RuntimeError("밀기 중 힘 데이터에 NaN/Inf가 포함되어 있습니다.")
        return values[1]

    def min_safe_tip_z(b_deg):
        return max(
            FLOOR_Z + FLOOR_MARGIN,
            FLANGE_MIN_Z + TCP_Z_OFFSET * math.cos(math.radians(b_deg)),
        )

    def check_tip_height(z, b_deg, step):
        min_z = min_safe_tip_z(b_deg)
        if z < min_z - 1e-6:
            raise RuntimeError(f"{step}: TCP Z={z:.2f} < 보호한계 Z={min_z:.2f} mm")

    def move_linear(label, pose, vel, acc):
        check_tip_height(pose[2], pose[4], label)
        print(f"=== {label} ===")
        checked(
            movel(posx(*pose), vel=vel, acc=acc, ref=DR_BASE),
            f"movel({label})",
        )

    def wait_motion_idle(label, timeout_sec=8.0):
        """첫 번째 털기 직전/직후 선행 모션이 IDLE이 될 때까지 확인."""
        deadline = time.monotonic() + timeout_sec
        while time.monotonic() < deadline:
            state = check_motion()
            if state == 0:
                return
            if state not in (1, 2):
                raise RuntimeError(f"{label}: 모션 상태 오류={state}")
            time.sleep(0.05)
        raise RuntimeError(f"{label}: {timeout_sec:.1f}초 동안 모션 종료 확인 실패")

    def enable_compliance():
        nonlocal compliance_active
        checked(
            task_compliance_ctrl(stx=COMPLIANCE_STIFFNESS),
            "task_compliance_ctrl",
        )
        compliance_active = True
        time.sleep(0.8)
        print(f"[순응제어 ON] stx={COMPLIANCE_STIFFNESS}")

    def disable_compliance():
        nonlocal compliance_active
        if compliance_active:
            if check_motion() != 0:
                raise RuntimeError("모션이 정지하지 않아 순응제어를 해제하지 않습니다.")
            checked(release_compliance_ctrl(), "release_compliance_ctrl")
            compliance_active = False
            print("[순응제어 OFF]")

    def descend_continuously(entry_rot):
        """한 번의 amovel로 하강하며 10N 감지 시 정지, 최대 100mm 및 기존 Z 하한 유지."""
        # 최신 예제와 동일한 정지 서비스. 설치된 드라이버의 경로를 먼저 확인.
        stop_client = None
        moving = False

        def stop_motion(mode=2):
            """진행 중인 모션을 정지 요청하고 check_motion()==0까지 확인."""
            state = check_motion()
            if state == 0:  # 이미 이동 종료된 경우
                return
            if state not in (1, 2):
                raise RuntimeError(f"정지 전 모션 상태 조회 오류: {state}")

            req = MoveStop.Request()
            req.stop_mode = mode  # 2: 느린 정지, 1: 빠른 정지
            future = stop_client.call_async(req)
            rclpy.spin_until_future_complete(node, future, timeout_sec=3.0)
            if not future.done() or future.result() is None or not future.result().success:
                raise RuntimeError("move_stop 정지 명령 실패")

            deadline = time.monotonic() + 5.0
            while time.monotonic() < deadline:
                state = check_motion()
                if state == 0:
                    return
                if state not in (1, 2):
                    raise RuntimeError(f"정지 중 모션 상태 조회 오류: {state}")
                time.sleep(0.02)
            raise RuntimeError("move_stop 후 정지 확인 실패")

        try:
            # 1) 해당 시스템의 정지 서비스 확인(드라이버별 네임스페이스 차이 대응).
            for service_name in STOP_SERVICE_NAMES:
                candidate = node.create_client(MoveStop, service_name)
                if candidate.wait_for_service(timeout_sec=1.0):
                    stop_client = candidate
                    print(f"[정지 서비스 연결] {service_name}")
                    break
                node.destroy_client(candidate)
            if stop_client is None:
                raise RuntimeError(
                    "MoveStop 서비스가 없습니다. ros2 service list | grep move_stop 으로 주소를 확인하세요."
                )
            if check_motion() != 0:
                raise RuntimeError("하강 시작 전 로봇 모션이 정지 상태가 아닙니다.")

            # 2) 정지 상태에서 기준 Fz를 한 번 측정.
            samples = []
            for _ in range(10):
                samples.append(read_tool_force_z())
                time.sleep(0.05)
            if max(samples) - min(samples) > 1.0:
                raise RuntimeError("하강 시작 전 기준 외력이 불안정합니다.")
            rest_fz = statistics.median(samples)

            start_pose = read_tcp_pose()
            start_z = start_pose[2]
            # 기존 100mm 거리 제한, 절대 Z=100mm 제한, TCP 높이 보호식 그대로 유지.
            limit_z = max(
                start_z - MAX_DESCENT_MM,
                MIN_DESCEND_Z,
                min_safe_tip_z(RY_ENTRY),
            )
            if start_z <= limit_z + 1e-6:
                raise RuntimeError(
                    f"하강 불가: 시작 Z={start_z:.2f} mm, 제한 Z={limit_z:.2f} mm"
                )
            print(
                f"[연속 하강] 시작 Z={start_z:.2f} mm, 목표 Z={limit_z:.2f} mm, "
                f"하강 한계={start_z-limit_z:.2f} mm, 속도={VEL_DESCENT} mm/s, "
                f"정지 기준 ΔFz={FORCE_THRESHOLD_N:.1f} N, 정지 Fz={rest_fz:+.2f} N"
            )

            # 3) 100mm 이내의 안전 목표까지 단 한 번 비동기 이동.
            target_pose = [START_X, START_Y, limit_z, *entry_rot]
            check_tip_height(limit_z, RY_ENTRY, "2: 연속 하강")
            moving = True  # amovel 호출 직전부터 중단 책임을 명시적으로 유지.
            checked(
                amovel(
                    posx(*target_pose),
                    vel=VEL_DESCENT,
                    acc=ACC_DESCENT,
                    ref=DR_BASE,
                ),
                "amovel(2: 연속 하강)",
            )

            moving_samples = []
            moving_baseline = None
            hits = 0
            max_delta = 0.0
            saw_motion = False
            started = time.monotonic()
            deadline = started + DESCENT_TIMEOUT_S

            while time.monotonic() < deadline:
                current = read_tcp_pose()
                force = read_tool_force_z()
                traveled = start_z - current[2]

                if (
                    abs(current[0] - start_pose[0]) > 2.0
                    or abs(current[1] - start_pose[1]) > 2.0
                    or current[2] < limit_z - 1.0
                    or traveled < -2.0
                ):
                    raise RuntimeError("하강 중 TCP 이동 경로 이탈")

                # 최초 8mm는 접촉 검출 대신 이동 중 동적 기준값을 수집.
                if traveled < 8.0:
                    if abs(force - rest_fz) >= 4.0:
                        raise RuntimeError("초기 8mm 하강 중 외력 이상")
                    if traveled >= 4.0:
                        moving_samples.append(force)
                else:
                    if moving_baseline is None:
                        if len(moving_samples) < 2:
                            raise RuntimeError(
                                "이동 중 기준 Fz 샘플 부족: 감시 속도 또는 하강 속도를 조정하세요."
                            )
                        moving_baseline = statistics.median(moving_samples)
                        print(f"[이동 중 Fz 기준값] {moving_baseline:+.2f} N")

                    delta = abs(force - moving_baseline)
                    max_delta = max(max_delta, delta)
                    hits = hits + 1 if delta >= FORCE_THRESHOLD_N else 0

                    if hits >= 2:
                        stop_motion(mode=2)  # 감지 후 정상 정지
                        moving = False
                        contact_pose = read_tcp_pose()  # 감속 완료 후 실제 접촉 위치
                        print(
                            f"[접촉 감지] ΔFz={delta:.2f} N, "
                            f"하강 거리={start_z-contact_pose[2]:.1f} mm, "
                            f"TCP Z={contact_pose[2]:.2f} mm"
                        )
                        if contact_pose[2] < limit_z - 1.0:
                            raise RuntimeError("정지 후 하강 제한 Z 이탈")
                        return contact_pose

                # 기존 하강 한계에 도달하고도 10N 2회 연속 감지되지 않으면 실패.
                if current[2] <= limit_z + 1.0:
                    stop_motion(mode=2)
                    moving = False
                    raise RuntimeError(
                        f"[하강 종료] {FORCE_THRESHOLD_N:.1f}N 미감지: "
                        f"시작 Z={start_z:.1f}, 제한 Z={limit_z:.1f}, "
                        f"실제 하강={start_z-current[2]:.1f}mm, 최대 ΔFz={max_delta:.2f}N"
                    )

                state = check_motion()
                if state in (1, 2):
                    saw_motion = True
                elif state == 0:
                    if saw_motion or time.monotonic() - started > 0.5:
                        moving = False  # 모션이 끝남. 잘못된 성공 반환 방지.
                        raise RuntimeError(
                            "10N 접촉 없이 하강 모션이 종료되었습니다. 스쿠핑을 중단합니다."
                        )
                else:
                    raise RuntimeError(f"하강 중 모션 상태 조회 오류: {state}")
                time.sleep(FORCE_SAMPLE_INTERVAL_S)

            raise TimeoutError("연속 하강 힘 감시 시간 초과")

        except BaseException as original_error:
            # 비동기 이동 중 예외만 던지고 방치하지 않도록 먼저 정지 요청.
            if moving and stop_client is not None:
                try:
                    stop_motion(mode=1)  # 이상 상황: 빠른 정지
                    moving = False
                except Exception as stop_error:
                    raise RuntimeError(
                        f"하강 오류 후 정지 확인 실패: {stop_error}. 로봇 안전 상태를 직접 확인하세요."
                    ) from original_error
            raise
        finally:
            if stop_client is not None:
                node.destroy_client(stop_client)

    def push_until_force_20n(entry_rot):
        """
        10N 하강 접촉 이후 순응제어 ON을 유지한 채
        DR_BASE 기준 -Y로 최대 200mm 연속 이동.
        밀기 시작 직전 Fy 기준값 대비 |ΔFy|>=20N 연속 2회 감지하면
        Soft Stop 후 실제 TCP 위치를 반환. 미감지 시 중단/예외.
        """
        if not compliance_active:
            raise RuntimeError("20N 밀기 전에 순응제어가 활성화되어 있어야 합니다.")

        stop_client = None
        moving = False

        def stop_push_motion(mode=2):
            """정지 서비스 성공 + check_motion()==0 확인."""
            state = check_motion()
            if state == 0:
                return
            if state not in (1, 2):
                raise RuntimeError(f"밀기 정지 전 모션 상태 오류: {state}")

            request = MoveStop.Request()
            request.stop_mode = mode
            future = stop_client.call_async(request)
            rclpy.spin_until_future_complete(node, future, timeout_sec=3.0)
            if not future.done() or future.result() is None or not future.result().success:
                raise RuntimeError("밀기 MoveStop 요청 실패")

            deadline = time.monotonic() + 5.0
            while time.monotonic() < deadline:
                state = check_motion()
                if state == 0:
                    return
                if state not in (1, 2):
                    raise RuntimeError(f"밀기 정지 확인 중 모션 상태 오류: {state}")
                time.sleep(0.02)
            raise RuntimeError("밀기 MoveStop 후 IDLE 확인 실패")

        try:
            # 기존 10N 하강 정지에 사용했던 정지 서비스 주소를 그대로 재사용.
            for service_name in STOP_SERVICE_NAMES:
                candidate = node.create_client(MoveStop, service_name)
                if candidate.wait_for_service(timeout_sec=1.0):
                    stop_client = candidate
                    print(f"[밀기 정지 서비스 연결] {service_name}")
                    break
                node.destroy_client(candidate)
            if stop_client is None:
                raise RuntimeError("밀기 중 정지할 MoveStop 서비스에 연결할 수 없습니다.")

            if check_motion() != 0:
                raise RuntimeError("20N 밀기를 시작하기 전에 이전 모션이 종료되지 않았습니다.")

            start_pose = read_tcp_pose()
            start_x, start_y, start_z = start_pose[:3]
            check_tip_height(start_z, entry_rot[1], "3-1: 20N 밀기 시작")

            # 기존 Z축 접촉 반력과 구분하기 위해, 밀기 직전 Y축 외력만 기준값 설정.
            time.sleep(0.2)
            fy_samples = []
            for _ in range(8):
                fy_samples.append(read_tool_force_y())
                time.sleep(0.04)
            if max(fy_samples) - min(fy_samples) > 3.0:
                raise RuntimeError("밀기 시작 전 Fy 외력 기준값이 불안정합니다.")
            baseline_fy = statistics.median(fy_samples)

            target_y = start_y - SCOOP_DIST_Y
            print(
                f"[20N 연속 밀기] 시작 Y={start_y:.2f}, 목표 Y={target_y:.2f} mm "
                f"(최대 {SCOOP_DIST_Y:.0f}mm), 기준 Fy={baseline_fy:+.2f} N"
            )

            moving = True
            checked(
                amovel(
                    posx(start_x, target_y, start_z, *entry_rot),
                    vel=VEL_SCOOP,
                    acc=ACC_SCOOP,
                    ref=DR_BASE,
                ),
                "amovel(3-1: -Y 방향 연속 밀기)",
            )

            hits = 0
            max_delta_fy = 0.0
            saw_motion = False
            started = time.monotonic()

            while time.monotonic() - started < PUSH_TIMEOUT_S:
                current = read_tcp_pose()
                fy = read_tool_force_y()
                traveled = start_y - current[1]
                delta_fy = abs(fy - baseline_fy)
                max_delta_fy = max(max_delta_fy, delta_fy)

                # 원래 스쿠핑 자세를 유지하며 -Y로만 이동하는지 확인.
                if (
                    abs(current[0] - start_x) > 2.0
                    or abs(current[2] - start_z) > 5.0
                    or traveled < -2.0
                    or traveled > SCOOP_DIST_Y + 1.0
                    or current[2] < min_safe_tip_z(entry_rot[1]) - 1.0
                ):
                    raise RuntimeError(
                        f"20N 밀기 중 이동 경로 이탈: "
                        f"Y 이동={traveled:.1f}mm / X={current[0]:.1f} / Z={current[2]:.1f}"
                    )

                hits = hits + 1 if delta_fy >= PUSH_FORCE_THRESHOLD_N else 0
                if hits >= 2:
                    stop_push_motion(mode=2)
                    moving = False
                    final_pose = read_tcp_pose()
                    actual_distance = start_y - final_pose[1]
                    print(
                        f"[20N 밀기 접촉 감지] ΔFy={delta_fy:.2f}N, "
                        f"정지 후 이동 거리={actual_distance:.1f}mm, "
                        f"최종 TCP Y={final_pose[1]:.2f}mm"
                    )
                    if actual_distance > SCOOP_DIST_Y + 1.0:
                        raise RuntimeError("20N 감지 후 정지 위치가 200mm 한계를 초과했습니다.")
                    return final_pose

                # 이미 명령 목표에 거의 도달했거나 비동기 모션 자체가 끝났다면 실패.
                if traveled >= SCOOP_DIST_Y - 1.0:
                    stop_push_motion(mode=2)
                    moving = False
                    raise RuntimeError(
                        f"[밀기 실패] {SCOOP_DIST_Y:.0f}mm까지 밀었으나 "
                        f"ΔFy {PUSH_FORCE_THRESHOLD_N:.0f}N 미감지 "
                        f"(최대 ΔFy={max_delta_fy:.2f}N)"
                    )

                motion_state = check_motion()
                if motion_state in (1, 2):
                    saw_motion = True
                elif motion_state == 0:
                    if saw_motion or time.monotonic() - started > 0.5:
                        moving = False
                        raise RuntimeError(
                            f"[밀기 실패] 모션은 종료됐지만 "
                            f"ΔFy {PUSH_FORCE_THRESHOLD_N:.0f}N에 도달하지 못했습니다."
                        )
                else:
                    raise RuntimeError(f"밀기 중 모션 상태 조회 오류: {motion_state}")

                time.sleep(PUSH_SAMPLE_INTERVAL_S)

            raise TimeoutError("20N 연속 밀기 감시 시간 초과")

        except BaseException as original_error:
            if moving and stop_client is not None:
                try:
                    stop_push_motion(mode=1)  # 오류 발생 시 빠른 정지 요청
                    moving = False
                except Exception as stop_error:
                    raise RuntimeError(
                        f"20N 밀기 오류 후 정지 확인 실패: {stop_error}; "
                        f"실제 로봇 정지 상태를 직접 확인하세요."
                    ) from original_error
            raise
        finally:
            if stop_client is not None:
                node.destroy_client(stop_client)

    try:
        # ======================================================
        # 1-0. Joint position -> choose pre-registered TCP
        # ======================================================
        print("=== 1-0: 초기 Joint 자세 ===")
        checked(set_robot_mode(ROBOT_MODE_AUTONOMOUS), "set_robot_mode(AUTO)")
        checked(movej(posj(*J_READY), vel=VEL_J_READY, acc=ACC_J_READY), "movej")

        if get_tcp() != TCP_NAME:
            checked(set_robot_mode(ROBOT_MODE_MANUAL), "set_robot_mode(MANUAL)")
            checked(set_tcp(TCP_NAME), "set_tcp(tcptest)")
            checked(set_robot_mode(ROBOT_MODE_AUTONOMOUS), "set_robot_mode(AUTO)")
        if get_tcp() != TCP_NAME:
            raise RuntimeError(f"활성 TCP가 {TCP_NAME!r}이 아닙니다.")
        checked(set_ref_coord(DR_BASE), "set_ref_coord(DR_BASE)")

        init_pose = read_tcp_pose()
        print(f"[TCP 확인] {get_tcp()}, 현재 Z={init_pose[2]:.2f} mm")

        # ======================================================
        # 1-1. Move X,Y and Z=220 mm while setting B=210, C=0
        # ======================================================
        entry_rot = [SCOOP_RX, RY_ENTRY, SCOOP_RZ]
        move_linear(
            f"1-1: X,Y,Z={START_Z:.0f} mm 이동 및 B={RY_ENTRY:.0f}°, C=0° 정렬",
            [START_X, START_Y, START_Z, *entry_rot],
            VEL_APPROACH,
            ACC_APPROACH,
        )

        if interactive:
            input("Enter를 누르면 순응제어 활성화 후 연속 하강하며 10N을 감지합니다...")

        # ======================================================
        # 2. Compliance -> 10-N contact or 100-mm distance guard
        # ======================================================
        enable_compliance()
        contact_pose = descend_continuously(entry_rot)

        # ======================================================
        # 3-1. 10N 하강 접촉 이후 순응제어 유지하며 -Y 방향 밀기
        #      ΔFy 20N 연속 2회 감지 시 정지 / 최대 200mm 미감지 시 오류
        # ======================================================
        push_pose = push_until_force_20n(entry_rot)
        print(f"[3-1 완료] 밀기 종료 TCP: {push_pose[:3]}")
        disable_compliance()

        # ======================================================
        # 3-2A. 20N 밀기 종료 지점에서 TCP XYZ 유지, B=180° 정렬
        # ======================================================
        after_scoop = read_tcp_pose()
        mid_rot = [SCOOP_RX, RY_MID, SCOOP_RZ]
        move_linear(
            f"3-2A: TCP XYZ 고정, B={RY_MID:.0f}° 정렬",
            [after_scoop[0], after_scoop[1], after_scoop[2], *mid_rot],
            VEL_ROTATE,
            ACC_ROTATE,
        )

        # ======================================================
        # 3-2B. 180°에서 130°까지 B를 바꾸면서 TCP의 Z만 상승
        #       movej()는 관절 경로이므로 TCP 직선 상승을 보장하지 않음.
        # ======================================================
        upright_pose = read_tcp_pose()     # B=180° 정렬 후 실제 TCP
        fixed_tip_x, fixed_tip_y, start_tip_z = upright_pose[:3]

        if LIFT_TARGET_Z <= start_tip_z:
            raise RuntimeError(
                f"TCP 상승 목표 Z={LIFT_TARGET_Z:.1f}mm가 현재 Z={start_tip_z:.1f}mm 이하입니다."
            )
        # 상승 경로 시작점/종점의 TCP 높이 확인. 공구 전체 충돌은 별도 검증 필요.
        check_tip_height(start_tip_z, RY_MID, "3-2B 시작")
        check_tip_height(LIFT_TARGET_Z, RY_LIFT, "3-2B 목표")
        print(
            f"=== 3-2B: TCP X={fixed_tip_x:.2f}, Y={fixed_tip_y:.2f} 고정, "
            f"Z={start_tip_z:.2f}→{LIFT_TARGET_Z:.2f}mm 상승 / "
            f"B={RY_MID:.0f}°→{RY_LIFT:.0f}° ==="
        )
        move_linear(
            "3-2B: 스푼 끝 TCP 수직 상승과 B=130도 동시 변경",
            [fixed_tip_x, fixed_tip_y, LIFT_TARGET_Z, SCOOP_RX, RY_LIFT, SCOOP_RZ],
            VEL_TCP_LIFT,
            ACC_TCP_LIFT,
        )
        lifted_tip_pose = read_tcp_pose()
        print(
            f"[3-2B 완료] TCP ΔX={lifted_tip_pose[0]-fixed_tip_x:+.2f}mm, "
            f"ΔY={lifted_tip_pose[1]-fixed_tip_y:+.2f}mm, "
            f"Z={lifted_tip_pose[2]:.2f}mm"
        )

        # ======================================================
        # 3-4. 첫 번째 Z축 털기 (B=130°)
        #       직전 movel 완전 종료 확인 후, 별도 저속 설정으로 실행.
        #       두 번째 털기(4-2A)의 설정과 실행부는 변경하지 않음.
        # ======================================================
        if SHAKE1_Z_MM > 0.0:
            # 첫 번째 털기 직전 모션 상태가 아직 MOVING으로 남아 있어도
            # 한 번의 check_motion()으로 실패 처리하지 않고 제한시간만큼 기다림.
            wait_motion_idle("3-4: 1차 털기 이전")
            time.sleep(0.2)   # movel→주기 운동 사이 짧은 안정화 간격
            shake_pose = read_tcp_pose()
            min_shake_z = max(MIN_DESCEND_Z, min_safe_tip_z(shake_pose[4]))
            if shake_pose[2] - SHAKE1_Z_MM < min_shake_z:
                raise RuntimeError(
                    f"1차 Z축 털기 불가: TCP Z={shake_pose[2]:.2f}mm, "
                    f"진폭={SHAKE1_Z_MM:.2f}mm, 허용 하한={min_shake_z:.2f}mm"
                )
            print(
                f"[3-4 1차 털기 시작] TCP={shake_pose}, "
                f"DR_BASE Z축 ±{SHAKE1_Z_MM:.1f}mm / "
                f"주기 {SHAKE1_PERIOD_SEC:.1f}초 / {SHAKE1_REPEAT}회",
                flush=True,
            )
            periodic_result = move_periodic(
                amp=[0.0, 0.0, SHAKE1_Z_MM, 0.0, 0.0, 0.0],
                period=[0.0, 0.0, SHAKE1_PERIOD_SEC, 0.0, 0.0, 0.0],
                atime=SHAKE1_ATIME_SEC,
                repeat=SHAKE1_REPEAT,
                ref=DR_BASE,
            )
            print(f"[3-4 1차 털기 반환] result={periodic_result}", flush=True)
            checked(periodic_result, "move_periodic(3-4: 1차 Z축 털기)")
            wait_motion_idle("3-4: 1차 털기 이후")
            print("[3-4 1차 털기 완료]", flush=True)
        else:
            print("[3-4 1차 털기 생략] SHAKE1_Z_MM=0", flush=True)

        # ======================================================
        # 4-1. TCP 상승 후 지정 TCP 목표 자세로 이동 (기존 movel 유지)
        #      요청 좌표는 관절각 posj가 아닌 DR_BASE 기준 posx로 해석
        # ======================================================
        after_lift = read_tcp_pose()
        print(f"[TCP 상승 완료] TCP Z={after_lift[2]:.2f}mm")
        move_linear(
            f"4-1: 지정 목표 TCP 이동 X={PLACE_X:.2f}, Y={PLACE_Y:.2f}, Z={PLACE_Z:.2f}, A={PLACE_A:.2f}, B={PLACE_B:.2f}, C={PLACE_C:.2f}",
            [PLACE_X, PLACE_Y, PLACE_Z, PLACE_A, PLACE_B, PLACE_C],
            VEL_TRANSFER,
            ACC_TRANSFER,
        )

        # ======================================================
        # 4-2. 도착 위치 고정 후 스푼(J6)만 180° 뒤집어서 내용물 투하 (movej)
        # ======================================================
        place_joints = read_joint_pose()
        flip_joints = list(place_joints)
        # M0609 J6 한계(±360°)를 넘지 않는 방향으로 180° 회전
        flip_joints[5] = (
            place_joints[5] - 180.0
            if place_joints[5] - 180.0 >= -350.0
            else place_joints[5] + 180.0
        )

        print(
            f"=== 4-2: 스푼(J6) 180° 뒤집기 (J6: {place_joints[5]:.1f}° → {flip_joints[5]:.1f}°) ==="
        )
        checked(
            movej(posj(*flip_joints), vel=VEL_DROP_FLIP, acc=ACC_DROP_FLIP),
            "movej(4-2: J6 뒤집기)",
        )

        # ======================================================
        # 4-2A. J6 180° 뒤집기 완료 후 Z축 move_periodic 털기 추가
        #        첫 번째 털기(3-4)와 동일한 진폭/주기/반복 설정 사용
        # ======================================================
        if SHAKE_Z_MM > 0.0:
            flipped_pose = read_tcp_pose()
            min_flip_shake_z = max(
                MIN_DESCEND_Z,
                min_safe_tip_z(flipped_pose[4]),
            )
            if flipped_pose[2] - SHAKE_Z_MM < min_flip_shake_z:
                raise RuntimeError(
                    f"J6 뒤집기 후 Z축 털기 불가: TCP Z={flipped_pose[2]:.2f}mm, "
                    f"진폭={SHAKE_Z_MM:.2f}mm, 하한={min_flip_shake_z:.2f}mm"
                )
            if check_motion() != 0:
                raise RuntimeError("J6 뒤집기 모션이 종료되지 않아 Z축 털기를 시작하지 않습니다.")

            print(
                f"=== 4-2A: J6 뒤집기 완료 후 Z축 ±{SHAKE_Z_MM:.1f}mm, "
                f"주기 {SHAKE_PERIOD_SEC:.1f}초, {SHAKE_REPEAT}회 ==="
            )
            checked(
                move_periodic(
                    amp=[0.0, 0.0, SHAKE_Z_MM, 0.0, 0.0, 0.0],
                    period=[0.0, 0.0, SHAKE_PERIOD_SEC, 0.0, 0.0, 0.0],
                    atime=SHAKE_ATIME_SEC,
                    repeat=SHAKE_REPEAT,
                    ref=DR_BASE,
                ),
                "move_periodic(4-2A: J6 뒤집기 후 Z축 털기)",
            )

        print(f"[투하 대기] 스푼 뒤집힌 상태로 {DROP_HOLD_SEC:.1f}초 대기...")
        time.sleep(DROP_HOLD_SEC)

        # ======================================================
        # 4-3. (옵션) 스푼(J6)을 다시 원래 각도로 복귀 (movej)
        # ======================================================
        if RETURN_UPRIGHT_AFTER_DROP:
            print(
                f"=== 4-3: 스푼(J6) 원위치 복귀 (J6: {flip_joints[5]:.1f}° → {place_joints[5]:.1f}°) ==="
            )
            checked(
                movej(posj(*place_joints), vel=VEL_DROP_RETURN, acc=ACC_DROP_RETURN),
                "movej(4-3: J6 복귀)",
            )

        final_joints = read_joint_pose()
        final_pose = read_tcp_pose()
        print("=== 전체 작업 완료 ===")
        print(
            f"최종 Joint: {[round(j, 2) for j in final_joints]}"
        )
        print(
            f"최종 TCP: X={final_pose[0]:.2f}, Y={final_pose[1]:.2f}, "
            f"Z={final_pose[2]:.2f} mm, Rx={final_pose[3]:.1f}°, Ry={final_pose[4]:.1f}°, Rz={final_pose[5]:.1f}°"
        )
        return (
            f"스쿠핑 및 투하 완료 "
            f"(X={final_pose[0]:.1f}, Y={final_pose[1]:.1f}, Z={final_pose[2]:.1f})"
        )

    except KeyboardInterrupt:
        print("[중단] 사용자 중단. 실제 로봇 모션/안전 상태를 확인하세요.")
        raise
    except Exception as exc:
        print(f"[오류] {exc}")
        raise
    finally:
        if compliance_active:
            try:
                disable_compliance()
            except Exception as exc:
                print(f"[경고] 순응제어 해제 실패 또는 모션 미종료: {exc}")
        try:
            ensure_default_tcp()
        except Exception as exc:
            print(f"[경고] 기본 TCP 원복 실패: {exc}")


def main(args=None):
    """단독 CLI 실행용 진입점."""
    rclpy.init(args=args)
    node = None
    try:
        DR_init.__dsr__id = ROBOT_ID
        DR_init.__dsr__model = ROBOT_MODEL
        node = rclpy.create_node("ice_cream_scoop_node", namespace=ROBOT_ID)
        DR_init.__dsr__node = node
        scoop_icecream(node=node, interactive=True)
    finally:
        if node is not None:
            node.destroy_node()
        rclpy.try_shutdown()


if __name__ == "__main__":
    main()