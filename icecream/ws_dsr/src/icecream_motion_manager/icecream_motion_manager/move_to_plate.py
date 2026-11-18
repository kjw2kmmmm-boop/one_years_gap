import rclpy
import DR_init

from icecream_motion_manager.motion_utils import wait_for_motion
from icecream_motion_manager.pose_config import get_motion_entry

ROBOT_ID = "dsr01"
ROBOT_MODEL = "m0609"


def move_to_plate():
    """poses.yaml의 plate 좌표(측정판 손잡이 위치)로 직선 이동한다."""
    from DSR_ROBOT2 import DR_BASE, DR_MV_MOD_ABS, amovel, posx

    plate_handle, vel, acc = get_motion_entry("plate")

    result = amovel(
        posx(*plate_handle),
        vel=vel,
        acc=acc,
        ref=DR_BASE,
        mod=DR_MV_MOD_ABS,
    )

    if result != 0:
        raise RuntimeError("측정판 이동 실패")

    wait_for_motion()
    print("측정판 이동 완료")


def main(args=None):
    """단독 CLI 실행용 진입점."""
    rclpy.init(args=args)
    node = None

    try:
        DR_init.__dsr__id = ROBOT_ID
        DR_init.__dsr__model = ROBOT_MODEL

        node = rclpy.create_node("move_to_plate", namespace=ROBOT_ID)
        DR_init.__dsr__node = node

        input("이동 경로 안전 확인 후 Enter: ")
        move_to_plate()
    finally:
        if node is not None:
            node.destroy_node()
        rclpy.try_shutdown()


if __name__ == "__main__":
    main()
