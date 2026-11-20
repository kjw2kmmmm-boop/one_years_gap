#!/usr/bin/env python3

import math
import time
import statistics
import rclpy
import DR_init

from dsr_msgs2.srv import MoveStop


ROBOT_ID = "dsr01"
ROBOT_MODEL = "m0609"

TARGET = [585.45, 17.47, 192.78, 0.63, -180.0, 90.0]

# 목표 위치 이동 설정
MOVE_SPEED = 70.0
MOVE_ACC = 70.0

# 하강 설정
DOWN_SPEED = 20.0
DOWN_ACC = 5.0
MAX_DOWN = 150.0

# 하강 중 외력 감지 설정
FORCE_LIMIT = 5.0
FORCE_HITS = 2
INTERVAL = 0.02

# 평탄화 설정
FLATTEN_DISTANCE = 200.0
FLATTEN_SPEED = 20.0
FLATTEN_ACC = 20.0

# 상승 설정
UP_SPEED = 80.0
UP_ACC = 80.0

TIMEOUT = 30.0


# 현재 TCP 좌표
def get_pose(robot):
    p = list(robot.get_current_posx(ref=robot.DR_BASE)[0])

    if len(p) != 6 or not all(map(math.isfinite, p)):
        raise RuntimeError("TCP 좌표 오류")

    return p


# 현재 외력
def get_force(robot):
    f = list(robot.get_tool_force(ref=robot.DR_BASE)[:3])

    if len(f) != 3 or not all(map(math.isfinite, f)):
        raise RuntimeError("외력 데이터 오류")

    return f


# 로봇 정지
def stop_motion(robot, node, client, mode=2):
    if robot.check_motion() == 0:
        return

    req = MoveStop.Request()
    req.stop_mode = mode

    future = client.call_async(req)
    rclpy.spin_until_future_complete(
        node, future, timeout_sec=3.0
    )

    if not future.done() or not future.result() or not future.result().success:
        raise RuntimeError("정지 명령 실패")

    deadline = time.monotonic() + 5.0

    while time.monotonic() < deadline:
        if robot.check_motion() == 0:
            return

        time.sleep(INTERVAL)

    raise RuntimeError("정지 확인 실패")


# 공통 이동 함수
def move(robot, stop, target, vel, acc, monitor=None):
    try:
        if robot.amovel(
            robot.posx(target),
            vel=vel,
            acc=acc,
            ref=robot.DR_BASE,
            mod=robot.DR_MV_MOD_ABS
        ) != 0:
            raise RuntimeError("이동 명령 실패")

        start = time.monotonic()
        was_moving = False

        while time.monotonic() - start < TIMEOUT:
            p = get_pose(robot)

            if monitor and monitor(p):
                stop(2)
                return True

            state = robot.check_motion()

            if state in (1, 2):
                was_moving = True

            elif state == 0:
                if math.dist(p[:3], target[:3]) <= 1.0:
                    return False

                if was_moving or time.monotonic() - start > 1.0:
                    raise RuntimeError("이동 중단")

            else:
                raise RuntimeError("모션 상태 오류")

            time.sleep(INTERVAL)

        raise TimeoutError("이동 시간 초과")

    except BaseException:
        stop(1)
        raise


# 1. 지정 좌표 이동
def approach(robot, stop):
    move(robot, stop, TARGET, MOVE_SPEED, MOVE_ACC)

    print("[1] 목표 위치 도착")

    # 하강하기 전 Z값 저장
    return get_pose(robot)[2]


# 2. 외력을 감지하며 하강
def descend(robot, stop):
    start = get_pose(robot)
    target = start.copy()
    target[2] -= MAX_DOWN

    samples = []

    for _ in range(10):
        samples.append(get_force(robot)[2])
        time.sleep(0.05)

    if max(samples) - min(samples) > 1.0:
        raise RuntimeError("초기 외력 불안정")

    rest_force = statistics.median(samples)

    moving_samples = []
    baseline = None
    hits = 0

    def monitor(p):
        nonlocal baseline, hits

        distance = start[2] - p[2]
        fz = get_force(robot)[2]

        if (
            abs(p[0] - start[0]) > 2.0
            or abs(p[1] - start[1]) > 2.0
            or p[2] < target[2] - 1.0
        ):
            raise RuntimeError("하강 경로 이탈")

        # 4~8mm 구간에서 이동 중 기준 외력 수집
        if distance < 8.0:
            if abs(fz - rest_force) >= 4.0:
                raise RuntimeError("초기 하강 중 외력 이상")

            if distance >= 4.0:
                moving_samples.append(fz)

            return False

        if baseline is None:
            if len(moving_samples) < 2:
                raise RuntimeError("외력 샘플 부족")

            baseline = statistics.median(moving_samples)
            print(f"이동 중 기준 외력: {baseline:.2f} N")

        delta = abs(fz - baseline)
        hits = hits + 1 if delta >= FORCE_LIMIT else 0

        if hits >= FORCE_HITS:
            print(f"[2] 접촉 감지: {delta:.2f} N")
            return True

        return False

    if not move(robot, stop, target, DOWN_SPEED, DOWN_ACC, monitor):
        raise RuntimeError("접촉 없이 최대 하강 거리 도달")


# 3. Y축 방향으로 평탄화 (외력 측정 없음)
def flatten(robot, stop):
    start = get_pose(robot)
    target = start.copy()
    target[1] += FLATTEN_DISTANCE

    def monitor(p):
        if (
            abs(p[0] - start[0]) > 2.0
            or abs(p[2] - start[2]) > 2.0
            or p[1] > target[1] + 1.0
        ):
            raise RuntimeError("평탄화 경로 이탈")

        return False

    move(robot, stop, target, FLATTEN_SPEED, FLATTEN_ACC, monitor)

    print("[3] 아이스크림 평탄화 완료")


# 4. 하강하기 전 높이로 상승
def lift(robot, stop, start_z):
    target = get_pose(robot)
    target[2] = start_z

    move(robot, stop, target, UP_SPEED, UP_ACC)

    print(f"[4] 기존 높이로 상승 완료: Z={start_z:.2f}")


# 전체 작업 실행
def flatten_icecream(node=None) -> str:
    """목표 좌표 이동 후 외력 감지 하강, Y축 평탄화, 원위치 상승을 수행한다."""
    if node is None:
        node = DR_init.__dsr__node
    if node is None:
        raise RuntimeError("DR_init.__dsr__node가 초기화되지 않았습니다.")

    import DSR_ROBOT2 as robot

    client = node.create_client(
        MoveStop,
        f"/{ROBOT_ID}/dsr_controller2/motion/move_stop",
    )

    try:
        if not client.wait_for_service(timeout_sec=3.0):
            raise RuntimeError("정지 서비스 연결 실패")

        if robot.check_motion() != 0 or robot.get_robot_state() != 1:
            raise RuntimeError("로봇 상태 확인 필요")

        def stop(mode=2):
            stop_motion(robot, node, client, mode)

        # 전체 동작 순서
        start_z = approach(robot, stop)
        descend(robot, stop)
        flatten(robot, stop)
        lift(robot, stop, start_z)

        print("전체 작업 완료")
        return f"아이스크림 평탄화 완료 (복귀 Z={start_z:.2f}mm)"
    finally:
        try:
            node.destroy_client(client)
        except Exception:
            pass


def main(args=None):
    rclpy.init(args=args)
    node = None

    try:
        DR_init.__dsr__id = ROBOT_ID
        DR_init.__dsr__model = ROBOT_MODEL

        node = rclpy.create_node("flatten", namespace=ROBOT_ID)
        DR_init.__dsr__node = node

        flatten_icecream(node=node)
    finally:
        if node is not None:
            node.destroy_node()

        if rclpy.ok():
            rclpy.try_shutdown()


if __name__ == "__main__":
    main()