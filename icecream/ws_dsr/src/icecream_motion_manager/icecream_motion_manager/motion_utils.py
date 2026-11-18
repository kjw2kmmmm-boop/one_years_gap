import time


def wait_for_motion(
    start_timeout: float = 0.5,
    poll_interval: float = 0.05,
    motion_timeout: float = 60.0,
) -> None:
    """비동기 모션(amovej/amovel)이 완료(IDLE=0)될 때까지 폴링 대기한다."""
    from DSR_ROBOT2 import check_motion

    start_deadline = time.monotonic() + start_timeout
    while time.monotonic() < start_deadline:
        status = check_motion()
        if status < 0:
            raise RuntimeError("모션 상태 확인(check_motion) 실패")
        if status != 0:
            break
        time.sleep(0.02)

    end_deadline = time.monotonic() + motion_timeout
    while True:
        status = check_motion()
        if status < 0:
            raise RuntimeError("모션 상태 확인(check_motion) 실패")
        if status == 0:
            return
        if time.monotonic() >= end_deadline:
            raise RuntimeError(f"모션 완료 대기 시간 초과 ({motion_timeout}s)")
        time.sleep(poll_interval)
