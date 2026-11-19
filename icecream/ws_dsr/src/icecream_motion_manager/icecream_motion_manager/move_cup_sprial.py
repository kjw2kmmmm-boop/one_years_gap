import math

import rclpy
import DR_init

from icecream_motion_manager.motion_utils import wait_for_motion
from icecream_motion_manager.pose_config import get_section_config

ROBOT_ID = "dsr01"
ROBOT_MODEL = "m0609"


def move_cup_sprial():
    """현재 위치에서 poses.yaml의 cup_spiral 파라미터(time 기준)로 나선형 스파이럴 모션을 수행한다."""
    from DSR_ROBOT2 import DR_BASE, amovesx, get_current_posx, posx

    cfg = get_section_config("cup_spiral")
    turns = int(cfg.get("turns", 5))
    radius = float(cfg.get("radius", 20.0))
    height = float(cfg.get("height", 60.0))
    points = int(cfg.get("points", 60))
    time_sec = float(cfg.get("time", 10.0))

    current, _sol = get_current_posx(ref=DR_BASE)
    if current is None:
        raise RuntimeError("현재 위치 확인 실패")

    cx = float(current[0]) - radius
    cy = float(current[1])
    cz = float(current[2])
    orient = [float(current[3]), float(current[4]), float(current[5])]

    path = []
    for i in range(1, points + 1):
        t = i / points
        angle = 2.0 * math.pi * turns * t
        r = radius * (1.0 - t)
        path.append(
            posx(
                cx + r * math.cos(angle),
                cy + r * math.sin(angle),
                cz - height * t,
                *orient,
            )
        )

    if time_sec > 0.0:
        result = amovesx(path, time=time_sec, ref=DR_BASE)
    else:
        vel = float(cfg.get("vel", 80.0))
        acc = float(cfg.get("acc", 80.0))
        result = amovesx(path, vel=vel, acc=acc, ref=DR_BASE)

    if result != 0:
        raise RuntimeError("컵 스파이럴 이동 실패")

    wait_for_motion()
    print("컵 스파이럴 이동 완료")


move_cup_spiral = move_cup_sprial


def main(args=None):
    """단독 CLI 실행용 진입점."""
    rclpy.init(args=args)
    node = None

    try:
        DR_init.__dsr__id = ROBOT_ID
        DR_init.__dsr__model = ROBOT_MODEL

        node = rclpy.create_node("icecream_spiral", namespace=ROBOT_ID)
        DR_init.__dsr__node = node

        move_cup_sprial()
    except Exception as exc:
        print(f"오류 발생: {exc}")
    finally:
        if node is not None:
            node.destroy_node()
        rclpy.try_shutdown()


if __name__ == "__main__":
    main()
