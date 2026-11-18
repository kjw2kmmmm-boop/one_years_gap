import time
import rclpy
import DR_init

from icecream_motion_manager.motion_utils import wait_for_motion
from icecream_motion_manager.pose_config import get_motion_entry

ROBOT_ID = "dsr01"
ROBOT_MODEL = "m0609"


def grip_and_lift():
    """그리퍼를 닫은 뒤 poses.yaml의 grip_and_lift 상대 좌표만큼 상승한다."""
    from DSR_ROBOT2 import DR_BASE, DR_MV_MOD_REL, amovel, posx, set_digital_output

    rel_pose, vel, acc = get_motion_entry("grip_and_lift", pose_key="rel_pose")

    print("그리퍼 닫기")

    if set_digital_output(2, 0) != 0:
        raise RuntimeError("DO2 OFF 실패")

    time.sleep(0.2)

    try:
        if set_digital_output(1, 1) != 0:
            raise RuntimeError("DO1 ON 실패")
        time.sleep(0.5)
    finally:
        off_result = set_digital_output(1, 0)

    if off_result != 0:
        raise RuntimeError("DO1 OFF 실패")

    time.sleep(3.0)

    print("Z축 상승")
    result = amovel(
        posx(*rel_pose),
        vel=vel,
        acc=acc,
        ref=DR_BASE,
        mod=DR_MV_MOD_REL,
    )

    if result != 0:
        raise RuntimeError("상승 실패")

    wait_for_motion()
    print("작업 완료")


def main(args=None):
    """단독 CLI 실행용 진입점."""
    rclpy.init(args=args)
    node = None

    try:
        DR_init.__dsr__id = ROBOT_ID
        DR_init.__dsr__model = ROBOT_MODEL

        node = rclpy.create_node("grip_and_lift", namespace=ROBOT_ID)
        DR_init.__dsr__node = node

        input("로봇 상태와 상승 경로 확인 후 Enter: ")
        grip_and_lift()
    finally:
        if node is not None:
            node.destroy_node()
        rclpy.try_shutdown()


if __name__ == "__main__":
    main()
