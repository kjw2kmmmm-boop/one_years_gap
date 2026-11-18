import rclpy
import DR_init

from icecream_motion_manager.motion_utils import wait_for_motion
from icecream_motion_manager.pose_config import get_motion_entry

ROBOT_ID = "dsr01"
ROBOT_MODEL = "m0609"


def move_to_scoop():
    """poses.yaml의 scoop 좌표를 읽어 수평 이동 후 수직 하강한다."""
    from DSR_ROBOT2 import (
        DR_BASE,
        DR_MV_MOD_ABS,
        amovel,
        get_current_posx,
        posx,
    )

    target_pos, vel, acc = get_motion_entry("scoop")

    current_pos, _sol = get_current_posx(ref=DR_BASE)
    if current_pos is None:
        raise RuntimeError("현재 위치 확인 실패")

    current_z = float(current_pos[2])
    if current_z <= target_pos[2]:
        raise RuntimeError("현재 Z가 목표 Z보다 낮거나 같습니다.")

    # 1. 현재 높이에서 목표 X, Y로 수평 이동
    approach = posx(
        target_pos[0],
        target_pos[1],
        current_z,
        target_pos[3],
        target_pos[4],
        target_pos[5],
    )

    # 2. 최종 목표 위치
    target = posx(*target_pos)

    print("1. 목표 X, Y로 수평 이동")
    result = amovel(
        approach,
        vel=vel,
        acc=acc,
        ref=DR_BASE,
        mod=DR_MV_MOD_ABS,
    )
    if result != 0:
        raise RuntimeError("수평 이동 실패")
    wait_for_motion()

    print("2. 목표 Z로 수직 하강")
    result = amovel(
        target,
        vel=vel,
        acc=acc,
        ref=DR_BASE,
        mod=DR_MV_MOD_ABS,
    )
    if result != 0:
        raise RuntimeError("수직 이동 실패")
    wait_for_motion()

    print("목표 좌표 이동 완료")


def main(args=None):
    """단독 CLI 실행용 진입점."""
    rclpy.init(args=args)
    node = None

    try:
        DR_init.__dsr__id = ROBOT_ID
        DR_init.__dsr__model = ROBOT_MODEL

        node = rclpy.create_node("move_spoon", namespace=ROBOT_ID)
        DR_init.__dsr__node = node

        input("이동 경로 안전 확인 후 Enter: ")
        move_to_scoop()
    except Exception as exc:
        print(f"오류 발생: {exc}")
    finally:
        if node is not None:
            node.destroy_node()
        rclpy.try_shutdown()


if __name__ == "__main__":
    main()
