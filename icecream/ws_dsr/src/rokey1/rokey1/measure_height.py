import math
import time

import rclpy
import DR_init

ROBOT_ID = "dsr01"
ROBOT_MODEL = "m0609"

# ========== 사용자 설정 ==========
MODE = "calibrate"       # calibrate / measure
BASE_Z = None            # 바닥 접촉 기준 TCP Z(mm)
ENABLE_MOTION = False    # 안전 확인 후 True

FORCE_LIMIT = 5.0        # 접촉 감지 기준(N)
STEP_MM = 0.5            # 한 번에 이동할 거리(mm)
MAX_DOWN = 15.0          # 최대 하강 거리(mm)
DOWN_SPEED = 2.0         # 이동 속도(mm/s)
FLOOR_MARGIN = 1.0       # 바닥 기준 여유 거리(mm)
MAX_SECONDS = 60.0       # 전체 측정 시간 제한


def get_pose(robot):
    """현재 TCP 좌표 읽기"""
    result = robot.get_current_posx(ref=robot.DR_BASE)

    try:
        pose = [float(v) for v in result[0]]
    except (TypeError, ValueError, IndexError):
        raise RuntimeError("TCP 좌표 수신 실패")

    if len(pose) != 6 or not all(map(math.isfinite, pose)):
        raise RuntimeError("TCP 좌표 데이터 오류")

    return pose


def get_force_z(robot):
    """베이스 좌표계 기준 Z축 외력 확인"""
    data = robot.get_tool_force(ref=robot.DR_BASE)

    try:
        values = [float(v) for v in data]
    except (TypeError, ValueError):
        raise RuntimeError("힘 센서 데이터 수신 실패")

    if len(values) != 6 or not all(map(math.isfinite, values)):
        raise RuntimeError("힘 센서 데이터 오류")

    return abs(values[2])


def stop_robot(node, client):
    """비정상 상황 발생 시 빠른 정지 요청"""
    from dsr_msgs2.srv import MoveStop

    request = MoveStop.Request()
    request.stop_mode = 1  # DR_QSTOP

    future = client.call_async(request)
    rclpy.spin_until_future_complete(
        node, future, timeout_sec=2.0
    )

    if not future.done():
        future.cancel()
        raise RuntimeError("정지 서비스 응답 시간 초과")

    result = future.result()

    if result is None or not result.success:
        raise RuntimeError("정지 요청 실패")


def measure_cup(node, robot):
    from DR_common2 import posx
    from dsr_msgs2.srv import MoveStop

    if BASE_Z is None or not math.isfinite(BASE_Z):
        raise RuntimeError("BASE_Z를 먼저 설정하세요")

    if robot.check_motion() != 0:
        raise RuntimeError("로봇이 정지 상태가 아닙니다")

    start = get_pose(robot)
    initial_force = get_force_z(robot)

    print(f"시작 Z: {start[2]:.2f} mm")
    print(f"초기 Z축 힘: {initial_force:.2f} N")

    if initial_force >= FORCE_LIMIT / 2:
        raise RuntimeError("시작 위치에 외력이 존재합니다")

    # 바닥 기준보다 아래로 내려가지 않도록 제한
    min_z = max(
        start[2] - MAX_DOWN,
        BASE_Z + FLOOR_MARGIN
    )

    if min_z >= start[2]:
        raise RuntimeError("하강 가능한 거리가 없습니다")

    # 비정상 상황에 대비해 정지 서비스 준비
    stop_client = node.create_client(
        MoveStop,
        f"/{ROBOT_ID}/dsr_controller2/motion/move_stop"
    )

    if not stop_client.wait_for_service(timeout_sec=3.0):
        raise RuntimeError("정지 서비스 연결 실패")

    print(f"최대 하강: {start[2] - min_z:.2f} mm")
    print("실제 이동 경로와 주변 장애물을 확인하세요.")

    if input("이동하려면 MOVE 입력: ").strip() != "MOVE":
        print("측정 취소")
        return None

    compliance = False
    moving = False
    contact_z = None

    try:
        # 순응 제어
        result = robot.task_compliance_ctrl(
            stx=[2000, 2000, 1000, 100, 100, 100],
            time=0.2
        )

        if result != 0:
            raise RuntimeError("순응 제어 시작 실패")

        compliance = True
        time.sleep(0.3)

        print("컵 높이 측정 시작")

        deadline = time.monotonic() + MAX_SECONDS

        while rclpy.ok():
            if time.monotonic() >= deadline:
                raise RuntimeError("측정 시간 초과")

            current = get_pose(robot)
            force = get_force_z(robot)

            # 접촉 확인
            if force >= FORCE_LIMIT:
                contact_z = current[2]
                print("컵 접촉 감지!")
                break

            # 최대 하강 거리 확인
            if current[2] <= min_z + 0.01:
                break

            # 현재 좌표에서 Z축만 조금 하강
            target = current.copy()
            target[2] = max(
                current[2] - STEP_MM,
                min_z
            )

            moving = True

            result = robot.movel(
                posx(target),
                vel=DOWN_SPEED,
                acc=5,
                ref=robot.DR_BASE
            )

            if result != 0:
                raise RuntimeError("하강 명령 실패")

            if robot.check_motion() != 0:
                raise RuntimeError("이동 완료 확인 실패")

            moving = False

            actual = get_pose(robot)

            # 실제 좌표가 비정상적인 경우 중단
            if actual[2] < min_z - 0.5:
                raise RuntimeError("하강 한계 초과")

            if actual[2] >= current[2] - 0.05:
                raise RuntimeError("로봇 이동이 확인되지 않음")

            print(
                f"Z: {actual[2]:.2f} mm | "
                f"힘: {get_force_z(robot):.2f} N"
            )

        if contact_z is None:
            raise RuntimeError("컵 미감지: 측정 중단")

        height = contact_z - BASE_Z

        if not (0 < height <= 500):
            raise RuntimeError("계산된 높이가 유효하지 않습니다")

        print("======================")
        print(f"접촉 Z: {contact_z:.2f} mm")
        print(f"컵 높이: {height:.2f} mm")
        print(f"컵 높이: {height / 10:.2f} cm")
        print("======================")

        print("측정 완료 - 자동 상승하지 않습니다")
        return height

    except BaseException:
        # 이동이 진행 중일 가능성이 있으면 정지 시도
        if moving:
            try:
                stop_robot(node, stop_client)
                moving = robot.check_motion() != 0
            except Exception as error:
                print(f"정지 확인 실패: {error}")

        if moving:
            print("경고: 로봇 정지 미확인! 티치펜던트 확인 필요")

        raise

    finally:
        # 정지 확인된 경우에만 순응 제어 해제
        if compliance and not moving:
            try:
                result = robot.release_compliance_ctrl()
                if result != 0:
                    print("순응 제어 해제 실패")
            except Exception as error:
                print(f"순응 제어 해제 오류: {error}")


def main(args=None):
    if MODE == "measure" and not ENABLE_MOTION:
        print("ENABLE_MOTION=False: 이동이 비활성화되었습니다.")
        return

    rclpy.init(args=args)

    DR_init.__dsr__id = ROBOT_ID
    DR_init.__dsr__model = ROBOT_MODEL

    node = rclpy.create_node(
        "cup_height_measure",
        namespace=ROBOT_ID
    )
    DR_init.__dsr__node = node

    try:
        import DSR_ROBOT2 as robot

        if MODE == "calibrate":
            if robot.check_motion() != 0:
                raise RuntimeError("로봇을 먼저 정지시키세요")

            z = get_pose(robot)[2]
            print(f"바닥 기준 Z = {z:.2f} mm")
            print("이 값을 확인 후 BASE_Z에 입력하세요")

        elif MODE == "measure":
            measure_cup(node, robot)

        else:
            raise ValueError("MODE는 calibrate 또는 measure")

    except KeyboardInterrupt:
        print("사용자가 실행을 중단했습니다")

    except Exception as error:
        print(f"오류: {error}")

    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == "__main__":
    main()