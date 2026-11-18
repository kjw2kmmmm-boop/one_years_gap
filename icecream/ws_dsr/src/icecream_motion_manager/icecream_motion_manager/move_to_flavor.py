import rclpy
import DR_init

from icecream_motion_manager.motion_utils import wait_for_motion
from icecream_motion_manager.pose_config import get_flavor_entry

ROBOT_ID = "dsr01"
ROBOT_MODEL = "m0609"


def move_to_flavor(flavor: str) -> str:
    """poses.yaml에서 지정한 아이스크림 맛 좌표를 읽어 직선 이동하고 표시명을 반환한다."""
    from DSR_ROBOT2 import DR_BASE, DR_MV_MOD_ABS, amovel, posx

    flavor_name, coords, vel, acc = get_flavor_entry(flavor)
    result = amovel(
        posx(*coords),
        vel=vel,
        acc=acc,
        ref=DR_BASE,
        mod=DR_MV_MOD_ABS,
    )
    if result != 0:
        raise RuntimeError(f"MoveL 명령 실패: {result}")

    wait_for_motion()
    print(f"{flavor_name} 위치 이동 명령 성공")
    return flavor_name


def main(args=None):
    """단독 CLI 실행용 진입점."""
    rclpy.init(args=args)
    node = None

    try:
        DR_init.__dsr__id = ROBOT_ID
        DR_init.__dsr__model = ROBOT_MODEL

        node = rclpy.create_node("move_to_flavor", namespace=ROBOT_ID)
        DR_init.__dsr__node = node

        print("===== 아이스크림 맛 선택 =====")
        print("1. 초코")
        print("2. 딸기")
        choice = input("맛을 선택하세요 (1/2): ").strip()

        flavor_name, coords, _vel, _acc = get_flavor_entry(choice)
        print(f"\n선택한 맛: {flavor_name}")
        print(f"목표 좌표: {coords}")

        input("\n이동 경로 및 주변 안전 확인 후 Enter: ")
        move_to_flavor(choice)
    except Exception as exc:
        print(f"오류 발생: {exc}")
    finally:
        if node is not None:
            node.destroy_node()
        rclpy.try_shutdown()


if __name__ == "__main__":
    main()
