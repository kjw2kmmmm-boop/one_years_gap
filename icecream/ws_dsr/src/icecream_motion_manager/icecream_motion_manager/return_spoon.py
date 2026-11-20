#!/usr/bin/env python3

import math
import time

import DR_init
import rclpy

from icecream_motion_manager.motion_utils import ensure_default_tcp


ROBOT_ID = "dsr01"
ROBOT_MODEL = "m0609"

# 스쿱을 내려놓는 위치
TARGET = [
    426.52, 222.05, 333.64,
    100.14, 179.96, 99.89,
]

# 이동 설정
MOVE_SPEED = 80.0
MOVE_ACC = 80.0
BLEND_RADIUS = 20.0

# 거치대 위 여유 높이
CLEARANCE = 80.0

# 스쿱 내려놓기 설정
DOWN_SPEED = 20.0
DOWN_ACC = 20.0

# 상승 설정
UP_SPEED = 80.0
UP_ACC = 80.0

# 그리퍼 설정
GRIP_PULSE = 0.5
GRIP_WAIT = 1.5


def check(result: int) -> None:
    """DSR 명령 반환값이 0이 아니면 예외를 발생시킨다."""
    if result != 0:
        raise RuntimeError(f"명령 실행 실패: {result}")


def get_pose(robot) -> list[float]:
    """현재 TCP 좌표(6축)를 조회하고 유효성을 검증한다."""
    p = list(robot.get_current_posx(ref=robot.DR_BASE)[0])

    if len(p) != 6 or not all(map(math.isfinite, p)):
        raise RuntimeError("현재 좌표 확인 실패")

    return [float(v) for v in p]


def move_line(robot, target: list[float], speed: float, acc: float) -> None:
    """목표 TCP 좌표로 직선 이동(movel)한다."""
    check(
        robot.movel(
            robot.posx(target),
            vel=speed,
            acc=acc,
            ref=robot.DR_BASE,
            mod=robot.DR_MV_MOD_ABS,
            radius=0.0,
        )
    )


def grip_release(robot) -> None:
    """그리퍼 열기 디지털 출력(DO1 OFF 후 DO2 펄스)을 전송한다."""
    check(robot.set_digital_output(1, 0))
    time.sleep(0.2)

    try:
        check(robot.set_digital_output(2, 1))
        time.sleep(GRIP_PULSE)
    finally:
        check(robot.set_digital_output(2, 0))

    time.sleep(GRIP_WAIT)
    print("그리퍼 열기 신호 전송 완료")


def approach(robot) -> None:
    """1. moveb를 이용해 스쿱 거치대 위로 안전 높이를 유지하며 이동한다."""
    current = get_pose(robot)

    safe_z = max(current[2], TARGET[2] + CLEARANCE)

    # 현재 위치에서 상승하는 경유점
    via = current.copy()
    via[2] = safe_z

    # 스쿱 거치대 위 목표 위치
    above = TARGET.copy()
    above[2] = safe_z

    lift_distance = safe_z - current[2]
    xy_distance = math.dist(current[:2], TARGET[:2])

    if lift_distance > 1.0 and xy_distance > 1.0:
        radius = min(
            BLEND_RADIUS,
            lift_distance / 4,
            xy_distance / 4,
        )

        path = [
            robot.posb(
                robot.DR_LINE,
                robot.posx(via),
                radius=radius,
            ),
            robot.posb(
                robot.DR_LINE,
                robot.posx(above),
                radius=0.0,
            ),
        ]

        check(
            robot.moveb(
                path,
                vel=MOVE_SPEED,
                acc=MOVE_ACC,
                ref=robot.DR_BASE,
                mod=robot.DR_MV_MOD_ABS,
            )
        )
    else:
        # 블렌딩할 경유점이 부족한 경우
        if lift_distance > 0.1:
            move_line(robot, via, MOVE_SPEED, MOVE_ACC)

        move_line(robot, above, MOVE_SPEED, MOVE_ACC)

    print("[1] 스쿱 거치대 위 도착")


def place_spoon(robot) -> None:
    """2. 스쿱 거치대 위치로 저속 수직 하강해 내려놓고 정지 및 오차를 확인한다."""
    move_line(robot, TARGET, DOWN_SPEED, DOWN_ACC)

    if robot.check_motion() != 0:
        raise RuntimeError("로봇 정지 확인 실패")

    if math.dist(get_pose(robot)[:3], TARGET[:3]) > 1.0:
        raise RuntimeError("스쿱 거치 위치 오차")

    print("[2] 스쿱 거치 위치 도착")


def lift(robot) -> None:
    """3. 스쿱을 내려놓은 뒤 거치대 위 여유 높이로 상승한다."""
    target = get_pose(robot)
    target[2] = TARGET[2] + CLEARANCE

    move_line(robot, target, UP_SPEED, UP_ACC)
    print("[4] 상승 완료")


def return_spoon(node=None) -> str:
    """스쿱 거치대 위로 이동해 내려놓고 그리퍼를 연 뒤 안전 높이로 상승한다."""
    if node is None:
        node = DR_init.__dsr__node
    if node is None:
        raise RuntimeError("DR_init.__dsr__node가 초기화되지 않았습니다.")

    import DSR_ROBOT2 as robot

    if robot.check_motion() != 0 or robot.get_robot_state() != 1:
        raise RuntimeError("로봇 정지 상태 확인 필요")

    ensure_default_tcp()
    check(robot.set_robot_mode(robot.ROBOT_MODE_AUTONOMOUS))

    approach(robot)
    place_spoon(robot)
    grip_release(robot)
    lift(robot)

    print("스쿱 복귀 완료")
    return (
        f"스쿱 거치 복귀 완료 "
        f"(X={TARGET[0]:.1f}, Y={TARGET[1]:.1f}, Z={TARGET[2]:.1f}, "
        f"상승 Z={TARGET[2] + CLEARANCE:.1f})"
    )


def main(args=None) -> None:
    """단독 CLI 실행용 진입점."""
    rclpy.init(args=args)
    node = None

    try:
        DR_init.__dsr__id = ROBOT_ID
        DR_init.__dsr__model = ROBOT_MODEL

        node = rclpy.create_node(
            "return_spoon",
            namespace=ROBOT_ID,
        )

        DR_init.__dsr__node = node
        return_spoon(node=node)
    finally:
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.try_shutdown()


if __name__ == "__main__":
    main()
