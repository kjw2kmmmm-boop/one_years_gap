import rclpy
import DR_init

from icecream_motion_manager.motion_utils import move_to_via
from icecream_motion_manager.pose_config import get_motion_entry, get_motion_via

ROBOT_ID = "dsr01"
ROBOT_MODEL = "m0609"


def move_cup_z():
    """poses.yaml의 cup_z 좌표로 movel을 사용해 Z→X→Y 3단계로 순차 이동한다."""
    from DSR_ROBOT2 import DR_BASE, DR_MV_MOD_ABS, get_current_posx, movel, posx

    via_section = get_motion_via("cup_z")
    if via_section:
        move_to_via(via_section)

    target_pos, vel, acc = get_motion_entry("cup_z")

    current_pos, _sol = get_current_posx(ref=DR_BASE)
    if current_pos is None:
        raise RuntimeError("현재 위치 확인 실패")

    cx, cy, cz = float(current_pos[0]), float(current_pos[1]), float(current_pos[2])
    crx, cry, crz = float(current_pos[3]), float(current_pos[4]), float(current_pos[5])
    tx, ty, tz, trx, try_, trz = [float(v) for v in target_pos]

    steps: list[tuple[str, list[float]]] = []
    if abs(cz - tz) > 0.1:
        steps.append(("1. Z축", [cx, cy, tz, crx, cry, crz]))
    if abs(cx - tx) > 0.1:
        steps.append(("2. X축", [tx, cy, tz, trx, try_, trz]))
    steps.append(("3. Y축", [tx, ty, tz, trx, try_, trz]))

    for step_label, coords in steps:
        print(f"[컵 측정 위치] {step_label} 이동 -> {coords[:3]}")
        result = movel(
            posx(*coords),
            vel=vel,
            acc=acc,
            ref=DR_BASE,
            mod=DR_MV_MOD_ABS,
        )
        if result != 0:
            raise RuntimeError(f"컵 측정 위치 {step_label} 이동 실패")

    print("컵 측정 위치 Z→X→Y 이동 완료")


def main(args=None):
    """단독 CLI 실행용 진입점."""
    rclpy.init(args=args)
    node = None

    try:
        DR_init.__dsr__id = ROBOT_ID
        DR_init.__dsr__model = ROBOT_MODEL

        node = rclpy.create_node("move_to_target", namespace=ROBOT_ID)
        DR_init.__dsr__node = node

        input("이동 경로 안전 확인 후 Enter: ")
        move_cup_z()
    except Exception as exc:
        print(f"오류 발생: {exc}")
    finally:
        if node is not None:
            node.destroy_node()
        rclpy.try_shutdown()


if __name__ == "__main__":
    main()
