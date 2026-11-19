import time
import rclpy
import DR_init

from icecream_motion_manager.motion_utils import ensure_default_tcp, wait_for_motion
from icecream_motion_manager.pose_config import get_motion_entry

ROBOT_ID = "dsr01"
ROBOT_MODEL = "m0609"


def grip_release():
    """그리퍼 열기 디지털 출력 신호를 전송한다."""
    from DSR_ROBOT2 import set_digital_output

    if set_digital_output(1, 0) != 0:
        raise RuntimeError("DO1 OFF 실패")

    time.sleep(0.2)

    try:
        if set_digital_output(2, 1) != 0:
            raise RuntimeError("DO2 ON 실패")
        time.sleep(0.5)
    finally:
        set_digital_output(2, 0)

    time.sleep(2.5)
    print("그리퍼 열기 신호 완료")


def move_home():
    """poses.yaml의 home 좌표로 이동시키고 그리퍼를 연다."""
    from DSR_ROBOT2 import amovej, posj

    home_joints, vel, acc = get_motion_entry("home", pose_key="joints")

    result = amovej(
        posj(*home_joints),
        vel=vel,
        acc=acc,
    )

    if result != 0:
        raise RuntimeError("HOME 이동 실패")

    wait_for_motion()
    grip_release()
    ensure_default_tcp()
    print("HOME 이동, 그리퍼 열기 및 기본 TCP 확인 완료")


def main(args=None):
    """단독 CLI 실행용 진입점."""
    rclpy.init(args=args)
    node = None

    try:
        DR_init.__dsr__id = ROBOT_ID
        DR_init.__dsr__model = ROBOT_MODEL

        node = rclpy.create_node("move_home", namespace=ROBOT_ID)
        DR_init.__dsr__node = node

        input("로봇 이동 경로 안전 확인 후 Enter: ")
        move_home()
    finally:
        if node is not None:
            node.destroy_node()
        rclpy.try_shutdown()


if __name__ == "__main__":
    main()
