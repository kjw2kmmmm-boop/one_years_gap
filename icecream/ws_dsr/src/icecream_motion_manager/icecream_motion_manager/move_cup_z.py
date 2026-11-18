import rclpy
import DR_init

from icecream_motion_manager.motion_utils import wait_for_motion
from icecream_motion_manager.pose_config import get_motion_entry

ROBOT_ID = "dsr01"
ROBOT_MODEL = "m0609"


def move_cup_z():
    """poses.yaml의 cup_z 좌표(컵 측정 위치)로 직선 이동한다."""
    from DSR_ROBOT2 import DR_BASE, DR_MV_MOD_ABS, amovel, posx

    target_pos, vel, acc = get_motion_entry("cup_z")

    result = amovel(
        posx(*target_pos),
        vel=vel,
        acc=acc,
        ref=DR_BASE,
        mod=DR_MV_MOD_ABS,
    )

    if result != 0:
        raise RuntimeError(f"이동 실패: {result}")

    wait_for_motion()
    print("목표 위치 이동 명령 완료")


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
