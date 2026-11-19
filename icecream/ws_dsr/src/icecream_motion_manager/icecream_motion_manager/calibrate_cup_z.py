import math
import os
import statistics
import time

import DR_init
import rclpy
from DR_common2 import posx
from dsr_msgs2.srv import MoveStop

from icecream_motion_manager.pose_config import get_section_config

ROBOT_ID = "dsr01"
ROBOT_MODEL = "m0609"

DEFAULT_CALIBRATION_PARAMS = {
    "gripper_mass_kg": 1.46,
    "tip_offset_z": -238.0,
    "ground_z": 15.0,
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
}


def _load_calibration_params() -> dict[str, float]:
    try:
        section = get_section_config("cup_calibration")
    except Exception:
        section = {}
    return {
        key: float(section.get(key, default))
        for key, default in DEFAULT_CALIBRATION_PARAMS.items()
    }


def calibration_cup_z(robot=None, node=None) -> float | None:
    """
    컵 위에서 하강 -> 접촉 감지 -> 상승.

    반환: 컵 높이(mm), 미감지: None
    """
    if robot is None:
        import DSR_ROBOT2 as robot_module

        robot = robot_module
    if node is None:
        node = DR_init.__dsr__node
    if node is None:
        raise RuntimeError("DR_init.__dsr__node가 초기화되지 않았습니다.")

    params = _load_calibration_params()
    robot_id = os.getenv("ROBOT_ID", getattr(DR_init, "__dsr__id", "") or ROBOT_ID).strip("/")

    gripper_mass_kg = params["gripper_mass_kg"]
    tip_offset_z = params["tip_offset_z"]
    ground_z = params["ground_z"]
    min_z = params["min_z"]
    start_clear_mm = params["start_clear_mm"]
    down_speed = params["down_speed"]
    down_acc = params["down_acc"]
    up_speed = params["up_speed"]
    up_acc = params["up_acc"]
    force_limit = params["force_limit"]
    start_abort_n = params["start_abort_n"]
    max_seconds = params["max_seconds"]
    check_interval = params["check_interval"]

    def get_pose() -> list[float]:
        result = robot.get_current_posx(ref=robot.DR_BASE)
        pose = [float(v) for v in result[0]]

        if len(pose) != 6 or not all(map(math.isfinite, pose)):
            raise RuntimeError("TCP 좌표 오류")

        return pose

    def get_force() -> float:
        force = float(robot.get_tool_force(ref=robot.DR_BASE)[2])
        if not math.isfinite(force):
            raise RuntimeError("힘 센서 오류")
        return force

    def wait_idle(
        timeout_sec: float = 10.0,
        error_label: str = "정지 확인 실패",
    ) -> None:
        deadline = time.monotonic() + timeout_sec

        while time.monotonic() < deadline:
            if robot.check_motion() == 0:
                z1 = get_pose()[2]
                time.sleep(0.15)

                if robot.check_motion() == 0 and abs(get_pose()[2] - z1) < 0.2:
                    return

            time.sleep(check_interval)

        raise RuntimeError(error_label)

    # ROS2 정지 서비스 연결
    stop_client = node.create_client(
        MoveStop,
        f"/{robot_id}/dsr_controller2/motion/move_stop",
    )

    if not stop_client.wait_for_service(timeout_sec=3.0):
        node.destroy_client(stop_client)
        raise RuntimeError("MoveStop 서비스 연결 실패")

    def stop_motion(mode: int) -> None:
        request = MoveStop.Request()
        request.stop_mode = mode

        future = stop_client.call_async(request)
        rclpy.spin_until_future_complete(node, future, timeout_sec=3.0)

        if not future.done():
            raise RuntimeError("정지 서비스 응답 시간 초과")

        result = future.result()
        if result is None or not result.success:
            raise RuntimeError("정지 명령 실패")

        wait_idle(timeout_sec=10.0, error_label="정지 확인 실패")

    moving = False

    try:
        if robot.check_motion() != 0:
            raise RuntimeError("로봇이 이동 중입니다")

        if robot.get_robot_state() != 1:
            raise RuntimeError("로봇이 STANDBY가 아닙니다")

        start = get_pose()

        if not ground_z < min_z < start[2] - start_clear_mm:
            raise RuntimeError("하강 범위 설정 오류")

        # 1. 정지 상태의 힘 측정
        samples = []
        for _ in range(10):
            samples.append(get_force())
            time.sleep(0.05)

        if max(samples) - min(samples) > 1.0:
            raise RuntimeError("초기 힘이 불안정합니다")

        rest_force = statistics.median(samples)

        print(f"시작 Z: {start[2]:.2f}mm")
        print(f"초기 힘: {rest_force:.2f}N")
        print(f"그리퍼 무게: {gripper_mass_kg}kg ({gripper_mass_kg * 9.81:.2f}N)")

        # 2. 연속 하강
        target = start.copy()
        target[2] = min_z

        moving = True
        result = robot.amovel(
            posx(target),
            vel=down_speed,
            acc=down_acc,
            ref=robot.DR_BASE,
            mod=robot.DR_MV_MOD_ABS,
        )

        if result != 0:
            raise RuntimeError("하강 명령 실패")

        deadline = time.monotonic() + max_seconds
        command_start = time.monotonic()

        moving_samples = []
        moving_baseline = None
        contact_z = None
        hits = 0
        motion_started = False

        print("측정판 하강 시작")

        # 3. 이동 중 외력 측정
        while time.monotonic() < deadline:
            current = get_pose()
            force = get_force()
            traveled = start[2] - current[2]

            # 이동 경로 검사
            if (
                abs(current[0] - start[0]) > 2.0
                or abs(current[1] - start[1]) > 2.0
                or current[2] < min_z - 1.0
            ):
                raise RuntimeError("이동 경로 이탈")

            # 처음 8mm는 검증된 비접촉 구간
            if traveled < start_clear_mm:
                if abs(force - rest_force) >= start_abort_n:
                    raise RuntimeError("시작 구간 힘 이상: Tool 설정 확인")

                if traveled >= start_clear_mm / 2:
                    moving_samples.append(force)
            else:
                if moving_baseline is None:
                    if len(moving_samples) < 2:
                        raise RuntimeError("이동 중 힘 기준 측정 실패")
                    moving_baseline = statistics.median(moving_samples)
                    print(f"이동 중 기준 힘: {moving_baseline:.2f}N")

                force_delta = abs(force - moving_baseline)

                if force_delta >= force_limit:
                    hits += 1
                else:
                    hits = 0

                if hits >= 2:
                    contact_z = current[2] + tip_offset_z
                    print(f"컵 접촉 감지: Z={contact_z:.2f}mm, 힘 변화={force_delta:.2f}N")

                    # 접촉 즉시 정지(DR_QSTOP)로 컵 과압 방지
                    stop_motion(1)
                    moving = False
                    break

            state = robot.check_motion()
            if state in (1, 2):
                motion_started = True
            elif state == 0:
                if abs(current[2] - min_z) < 1.0:
                    moving = False
                    print("컵 미감지")
                    break

                if motion_started:
                    raise RuntimeError("예상하지 못한 이동 종료")

                if time.monotonic() - command_start > 5.0:
                    raise RuntimeError("이동 시작 확인 실패")
            else:
                raise RuntimeError(f"알 수 없는 이동 상태: {state}")

            time.sleep(check_interval)
        else:
            raise RuntimeError("측정 시간 초과")

        # 4. 원위치 상승
        if robot.get_robot_state() != 1:
            raise RuntimeError("로봇이 STANDBY가 아니어서 상승 중단")

        print("원위치 상승 시작")
        moving = True

        result = robot.amovel(
            posx(start),
            vel=up_speed,
            acc=up_acc,
            ref=robot.DR_BASE,
            mod=robot.DR_MV_MOD_ABS,
            radius=0.0,
        )

        if result != 0:
            raise RuntimeError("상승 실패")

        start_deadline = time.monotonic() + 0.5
        while time.monotonic() < start_deadline:
            if robot.check_motion() != 0:
                break
            time.sleep(check_interval)

        wait_idle(
            timeout_sec=max(30.0, max_seconds),
            error_label="상승 완료 확인 실패",
        )
        moving = False

        if abs(get_pose()[2] - start[2]) > 0.5:
            raise RuntimeError("상승 위치 오차")

        print("원위치 상승 완료")

        # 5. 컵 높이 계산
        if contact_z is None:
            print("컵 미감지")
            return None

        height = contact_z - ground_z - 20.00

        print("========================")
        print(f"그리퍼 보정값: {tip_offset_z:.2f}mm")
        print(f"보정된 접촉 Z: {contact_z:.2f}mm")
        print(f"컵 높이: {height:.2f}mm")
        print(f"컵 높이: {height / 10:.2f}cm")
        print("========================")

        return height

    except BaseException:
        if moving:
            try:
                stop_motion(1)
                print("빠른 정지 요청 완료")
            except Exception as error:
                print(f"정지 확인 실패: {error}")

        print("측정 중단: 로봇 상태 확인 필요")
        raise

    finally:
        node.destroy_client(stop_client)


calibrate_cup_z = calibration_cup_z


def main():
    rclpy.init()

    DR_init.__dsr__id = ROBOT_ID
    DR_init.__dsr__model = ROBOT_MODEL

    node = rclpy.create_node("cup_height_measure", namespace=ROBOT_ID)
    DR_init.__dsr__node = node

    try:
        import DSR_ROBOT2 as robot

        print("측정판이 컵보다 최소 8mm 높게 있는지")
        print("실제로 확인한 경우에만 실행하세요.")

        if input("시작하려면 MOVE 입력: ").strip() != "MOVE":
            print("측정 취소")
            return

        cup_height = calibration_cup_z(robot, node)

        if cup_height is not None:
            print(f"최종 컵 높이: {cup_height:.2f}mm")

    except KeyboardInterrupt:
        print("사용자 중단: 로봇 상태 확인 필요")

    except Exception as error:
        print(f"오류: {error}")

    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == "__main__":
    main()
