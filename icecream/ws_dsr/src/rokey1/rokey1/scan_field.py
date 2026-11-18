import rclpy
import DR_init
import time
from collections import deque
from datetime import datetime, timedelta

# for single robot
ROBOT_ID   = "dsr01"
ROBOT_MODEL= "m0609"
VELOCITY, ACC = 100, 100
SCAN_VEL, SCAN_ACC = 20, 40  # 물컵이 밀리지 않도록 스캔 속도는 낮추고(20), 가속 구간은 단축(40)

DR_init.__dsr__id   = ROBOT_ID
DR_init.__dsr__model= ROBOT_MODEL

ON, OFF = 1, 0
CYCLE = 1
CHECK_INTERVAL = 0.02        # 20ms마다 빠르게 폴링 (중복 프레임은 자동 스킵)
WARMUP_TIME = 0.8            # 출발 가속 노이즈 무시 시간 (초)
FORCE_THRESHOLD_X = 1.0      # X축 충돌 감지 임계값 (평소 노이즈 최대 ~0.3N)
FORCE_THRESHOLD_Y = 1.1      # Y축 충돌 감지 임계값 (평소 노이즈 최대 ~0.55N)
WINDOW_SIZE = 3              # 직전 3개 샘플의 단기 이동평균 (자세 변화 누적 방지)
LAG_SIZE = 1                 # 직전 1틱(0.1초)만 분리하여 순간 상승 시 평균 희석 방지 및 드리프트 최소화
MIN_SAMPLES = 3              # 비교 시작 전 최소 고유 샘플 수


def main(args=None):
    rclpy.init(args=args)
    node = rclpy.create_node("m0609_gear", namespace=ROBOT_ID)

    DR_init.__dsr__node = node

    try:
        from DSR_ROBOT2 import (
            set_digital_output,
            get_digital_input,
            set_tool,
            set_tcp,
            set_ref_coord,
            movej,
            movel,
            amovel,
            check_motion,
            get_tool_force,
            wait,
            move_periodic,
            task_compliance_ctrl,
            set_stiffnessx,
            set_desired_force,
            check_force_condition,
            release_force,
            release_compliance_ctrl,
            DR_MV_RA_DUPLICATE,
            DR_MV_MOD_ABS,
            DR_MV_APP_NONE,
            DR_MV_MOD_REL,
            DR_FC_MOD_ABS,
            DR_AXIS_Z,
            DR_TOOL,
            DR_QSTOP,
            DR_SSTOP,
        )
        from dsr_msgs2.srv import MoveStop
        from DR_common2 import posj, posx

    except ImportError as e:
        node.get_logger().info(f"Error importing DSR_ROBOT2 : {e}")
        return

    # DSR_ROBOT2.py에 누락된 공식 MoveStop 서비스 클라이언트 연결
    stop_client = node.create_client(MoveStop, "dsr_controller2/motion/move_stop")

    def stop_robot(stop_mode=DR_QSTOP):
        req = MoveStop.Request()
        req.stop_mode = int(stop_mode)
        future = stop_client.call_async(req)
        rclpy.spin_until_future_complete(node, future)
        return future.result()

    set_tool("Tool Weight_1")
    set_tcp("GripperDA_v1")
    set_ref_coord(DR_TOOL)

    homej = posj([0, 0, 90, 0, 90, 0])
    init_start = posj([37.70, 4.74, 111.96, -0.09, 64.62, 14.17])

    movej(homej, vel=VELOCITY, acc=ACC)

    collision_detected = False

    try:
        for i in range(CYCLE):
            node.get_logger().info(f"=== Cycle {i+1}/{CYCLE} ===")

            # 1. 시작 위치(init_start)로 이동 후 잔진동 안정화 대기
            movej(init_start, vel=VELOCITY, acc=ACC)
            wait(0.5)

            # 오차 평균 계산을 위한 슬라이딩 윈도우 버퍼 (x, y, z)
            fx_window = deque(maxlen=WINDOW_SIZE)
            fy_window = deque(maxlen=WINDOW_SIZE)
            fz_window = deque(maxlen=WINDOW_SIZE)
            # 순간 상승 중인 값(최근 LAG_SIZE개)이 곧바로 평균에 섞여 diff를 줄이는 것을 막기 위한 지연 큐
            lag_buffer = deque()

            # 2. DR_TOOL 기준 -y 방향으로 비동기 상대 이동 시작
            node.get_logger().info("Start scanning: moving along -Y (DR_TOOL)...")
            amovel(
                posx([0, -500, 0, 0, 0, 0]),
                vel=SCAN_VEL,
                acc=SCAN_ACC,
                ref=DR_TOOL,
                mod=DR_MV_MOD_REL,
            )

            # 실제로 모션이 시작될 때까지 대기 (IDLE 상태 통과)
            wait_start = time.time()
            while check_motion() == 0 and (time.time() - wait_start) < 1.0:
                time.sleep(0.02)

            # 출발 직후 가속 구간(관성/정지마찰로 힘이 튀는 구간) 흘려보내기
            node.get_logger().info(f"Stabilizing initial acceleration for {WARMUP_TIME}s...")
            time.sleep(WARMUP_TIME)

            # 3. 등속 이동 상태에서 오차평균 수집 및 diff 급증(충돌) 감지 루프
            prev_forces = None
            while check_motion() != 0:
                forces = get_tool_force(DR_TOOL)
                if forces == -1 or len(forces) < 3:
                    time.sleep(CHECK_INTERVAL)
                    continue

                fx, fy, fz = forces[0], forces[1], forces[2]
                cur_forces = (fx, fy, fz)

                # 제어기(100ms 주기)에서 아직 갱신되지 않은 중복 프레임은 건너뛰어 평균 왜곡 방지
                if cur_forces == prev_forces:
                    time.sleep(CHECK_INTERVAL)
                    continue
                prev_forces = cur_forces

                # 이동 중 최소 샘플(MIN_SAMPLES)이 모인 뒤부터 직전 오차평균과 비교
                if len(fx_window) >= MIN_SAMPLES:
                    avg_fx = sum(fx_window) / len(fx_window)
                    avg_fy = sum(fy_window) / len(fy_window)
                    avg_fz = sum(fz_window) / len(fz_window)

                    diff_x = abs(fx - avg_fx)
                    diff_y = abs(fy - avg_fy)

                    node.get_logger().info(
                        f"Force(N) Cur: [X:{fx:.2f}, Y:{fy:.2f}, Z:{fz:.2f}] | "
                        f"Avg: [X:{avg_fx:.2f}, Y:{avg_fy:.2f}, Z:{avg_fz:.2f}] | "
                        f"Diff: [dX:{diff_x:.2f}, dY:{diff_y:.2f}]"
                    )

                    # 4. diff가 확 오를 때(직전 이동평균 대비 임계값 이상 급변) 즉시 정지 (z축 무시)
                    if diff_x >= FORCE_THRESHOLD_X or diff_y >= FORCE_THRESHOLD_Y:
                        node.get_logger().warn(
                            f"Collision Detected! Spike in diff (dX={diff_x:.2f}N [th:{FORCE_THRESHOLD_X}N], "
                            f"dY={diff_y:.2f}N [th:{FORCE_THRESHOLD_Y}N]). Stopping in place!"
                        )
                        stop_robot(DR_QSTOP)
                        collision_detected = True
                        break
                    # 현재 값을 곧바로 평균에 넣으면 0.2~0.3초 동안 치솟는 값이 평균까지 같이 끌어올려
                    # diff가 줄어드는 현상이 발생하므로, 최근 LAG_SIZE틱(0.3초)만큼 지연시켜 평균에 반영
                    lag_buffer.append((fx, fy, fz))
                    if len(lag_buffer) > LAG_SIZE:
                        old_fx, old_fy, old_fz = lag_buffer.popleft()
                        fx_window.append(old_fx)
                        fy_window.append(old_fy)
                        fz_window.append(old_fz)
                else:
                    node.get_logger().info(
                        f"Collecting moving baseline... ({len(fx_window) + 1}/{MIN_SAMPLES}) "
                        f"Cur: [X:{fx:.2f}, Y:{fy:.2f}, Z:{fz:.2f}]"
                    )
                    fx_window.append(fx)
                    fy_window.append(fy)
                    fz_window.append(fz)

                time.sleep(CHECK_INTERVAL)

            if collision_detected:
                node.get_logger().info("Robot stopped in place due to object detection.")
                break
            else:
                node.get_logger().info("Scan move finished without collision.")

        node.get_logger().info("Scan Field Complete")

    except KeyboardInterrupt:
        node.get_logger().info("Program Stopped")
        stop_robot(DR_SSTOP)
        
    except TimeoutError as e:
        node.get_logger().error(str(e))

    finally:
        # 충돌 감지 시에는 그 자리에 그대로 멈춰야 하므로 홈 복귀 생략
        if not collision_detected:
            try:
                movej(homej, vel=VELOCITY, acc=ACC)
            except Exception as e:
                node.get_logger().error(f"Failed to move home: {e}")

        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()

