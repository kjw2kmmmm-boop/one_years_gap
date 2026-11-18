import time
import rclpy
import DR_init

ROBOT_ID = "dsr01"
ROBOT_MODEL = "m0609"


def _pulse_digital_output(
    off_channel: int,
    on_channel: int,
    pulse_sec: float = 2.5,
    settle_sec: float = 3.0,
) -> None:
    """지정 채널을 OFF한 뒤 다른 채널에 펄스 신호를 출력한다."""
    from DSR_ROBOT2 import set_digital_output

    def output(channel: int, value: int) -> None:
        if set_digital_output(channel, value) != 0:
            raise RuntimeError(f"DO{channel} 출력 실패")

    output(off_channel, 0)

    try:
        output(on_channel, 1)
        time.sleep(pulse_sec)
    finally:
        output(on_channel, 0)

    time.sleep(settle_sec)


def griper_release() -> None:
    """그리퍼 열기: DO1 OFF 후 DO2 펄스 출력."""
    _pulse_digital_output(off_channel=1, on_channel=2)
    print("그리퍼 열기 신호 완료")


def griper_grap() -> None:
    """그리퍼 닫기: DO2 OFF 후 DO1 펄스 출력."""
    _pulse_digital_output(off_channel=2, on_channel=1)
    print("그리퍼 닫기 신호 완료")


grip_open = griper_release
grip_close = griper_grap


def _run_cli(node_name: str, action) -> None:
    rclpy.init()
    node = None
    try:
        DR_init.__dsr__id = ROBOT_ID
        DR_init.__dsr__model = ROBOT_MODEL

        node = rclpy.create_node(node_name, namespace=ROBOT_ID)
        DR_init.__dsr__node = node

        input("그리퍼 주변 안전 확인 후 Enter: ")
        action()
    finally:
        if node is not None:
            node.destroy_node()
        rclpy.try_shutdown()


def main_release(args=None) -> None:
    del args
    _run_cli("grip_open", griper_release)


def main_grap(args=None) -> None:
    del args
    _run_cli("grip_close", griper_grap)


if __name__ == "__main__":
    main_release()
