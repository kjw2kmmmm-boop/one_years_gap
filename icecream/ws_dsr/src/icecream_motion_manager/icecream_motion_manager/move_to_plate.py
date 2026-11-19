import rclpy
import DR_init

from icecream_motion_manager.motion_utils import move_section_with_via

ROBOT_ID = "dsr01"
ROBOT_MODEL = "m0609"


def move_to_plate():
    """poses.yaml의 plate 좌표로 경유 모서리를 블렌딩하며 이동한다."""
    move_section_with_via("plate", label="측정판", use_blending=True)
    print("측정판 블렌딩 이동 완료")


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
