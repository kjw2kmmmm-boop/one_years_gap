import rclpy
import DR_init
import time
from datetime import datetime, timedelta

# for single robot
ROBOT_ID   = "dsr01"
ROBOT_MODEL= "m0609"
VELOCITY, ACC = 100, 100

DR_init.__dsr__id   = ROBOT_ID
DR_init.__dsr__model= ROBOT_MODEL

ON, OFF = 1, 0
CYCLE = 1
CHECK_INTERVAL = 0.1


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
        )

        from DR_common2 import posj, posx

    except ImportError as e:
        node.get_logger().info(f"Error importing DSR_ROBOT2 : {e}")
        return

    set_tool("Tool Weight_1")
    set_tcp("GripperDA_v1")

    # =========================================================================
    # 좌표 리스트 정리 (m0609.drl 기준)
    # =========================================================================
    homej = posj([0, 0, 90, 0, 90, 0])

    # 공통 상대 이동 좌표 (Y축 -300mm 이동)
    rel_move_posx = posx([0.00, -300.00, 0.00, 0.00, 0.00, 0.00])

    # 1. 외곽 기어 (gear_1, gear_2, gear_3) 좌표 리스트
    # [0]: gear_1, [1]: gear_2, [2]: gear_3
    gear_pick_posj_list = [
        posj([20.40, 7.49, 105.32, -0.07, 67.19, 19.35]),  # gear_1 잡기 위치
        posj([23.64, 21.35, 87.33, -0.97, 71.43, 22.36]),  # gear_2 잡기 위치
        posj([11.07, 17.64, 92.54, -0.12, 69.83, 7.30]),   # gear_3 잡기 위치
    ]

    gear_up_posx_list = [
        posx([361.53, 148.15, 350.00, 107.12, -178.48, 105.71]),  # gear_1 들어올리기 (Z=350)
        posx([452.65, 204.98, 350.00, 106.76, -179.20, 104.94]),  # gear_2 들어올리기 (Z=350)
        posx([458.54, 97.79, 350.00, 12.18, -179.99, 8.14]),      # gear_3 들어올리기 (Z=350)
    ]

    gear_place_posx_list = [
        posx([361.50, -151.84, 280.00, 107.00, -178.48, 105.59]),  # gear_1 내려놓기 (Z=280)
        posx([452.65, -95.02, 280.00, 106.92, -179.20, 105.10]),   # gear_2 내려놓기 (Z=280)
        posx([458.53, -202.19, 280.00, 36.30, -179.99, 32.26]),    # gear_3 내려놓기 (Z=280)
    ]

    # 2. 중앙 기어 (gear_center) 좌표 리스트
    center_pick_posj = posj([18.07, 15.10, 96.08, -0.11, 68.82, 20.47])
    center_posx_list = [
        posx([427.50, 146.86, 350.00, 21.49, -180.00, 23.61]),    # [0] 들어올리기 (Z=350)
        posx([427.49, -153.13, 295.00, 170.40, 180.00, 172.52]),  # [1] 안착 접근 1 (Z=295)
        posx([427.49, -153.13, 290.00, 138.05, -180.00, 140.17]), # [2] 안착 접근 2 (Z=290)
    ]

    # 3. 힘/순응 제어 및 주기 모션 파라미터 리스트
    stiffness_list = [3000.00, 3000.00, 3000.00, 200.00, 200.00, 200.00]
    desired_force_list = [0.00, 0.00, 10.00, 0.00, 0.00, 0.00]
    force_dir_list = [0, 0, 1, 0, 0, 0]
    periodic_amp_list = [0.00, 0.00, 0.00, 0.00, 0.00, 6.00]
    periodic_period_list = [0.00, 0.00, 0.00, 0.00, 0.00, 0.50]

    # =========================================================================
    # 동작 함수 정의
    # =========================================================================
    def grip():
        node.get_logger().info("set for digital output 1 0 for grip")

        # 초기화
        set_digital_output(1, OFF)
        set_digital_output(2, OFF)

        # 실행
        set_digital_output(1, ON)
        set_digital_output(2, OFF)

        # wait(1)
        time.sleep(1)

    def release():
        node.get_logger().info("set for digital output 0 1 for release")
        set_digital_output(1, OFF)
        set_digital_output(2, OFF)
        set_digital_output(1, OFF)
        set_digital_output(2, ON)
        wait(1)

    def gear_periodic():
        node.get_logger().info("Executing gear_periodic")
        move_periodic(
            amp=periodic_amp_list,
            period=periodic_period_list,
            atime=1.00,
            repeat=5,
            ref=0,
        )

    def detecting_gear():
        node.get_logger().info("Detecting gear with compliance & force control")
        set_ref_coord(1)
        task_compliance_ctrl()
        set_stiffnessx(stiffness_list, time=0.0)
        set_desired_force(
            desired_force_list,
            force_dir_list,
            time=0.0,
            mod=DR_FC_MOD_ABS,
        )

        while True:
            if check_force_condition(axis=DR_AXIS_Z, min=10, ref=DR_TOOL):
                break
            time.sleep(CHECK_INTERVAL)

        gear_periodic()
        release_force(time=0.0)
        release_compliance_ctrl()

    def gears():
        for idx, (pick_posj, up_posx, place_posx) in enumerate(
            zip(gear_pick_posj_list, gear_up_posx_list, gear_place_posx_list),
            start=1,
        ):
            node.get_logger().info(f"Moving gear_{idx}")

            # 1. 기어 잡는 위치로 관절 이동
            movej(
                pick_posj,
                radius=0.00,
                ra=DR_MV_RA_DUPLICATE,
                acc=ACC,
                vel=VELOCITY,
            )

            # 2. 그리퍼 잡기
            grip()

            # 3. 들어올리기 (Z=350)
            movel(
                up_posx,
                radius=0.00,
                ref=0,
                mod=DR_MV_MOD_ABS,
                ra=DR_MV_RA_DUPLICATE,
                acc=ACC,
                vel=VELOCITY,
            )

            # 4. Y축 상대 이동 (-300mm)
            movel(
                rel_move_posx,
                radius=0.00,
                ref=0,
                mod=DR_MV_MOD_REL,
                ra=DR_MV_RA_DUPLICATE,
                acc=ACC,
                vel=VELOCITY,
            )

            # 5. 조립 위치에 내려놓기 (Z=280)
            movel(
                place_posx,
                radius=0.00,
                ref=0,
                mod=DR_MV_MOD_ABS,
                ra=DR_MV_RA_DUPLICATE,
                acc=ACC,
                vel=VELOCITY,
            )

            # 6. 그리퍼 놓기
            release()

    def gear_center():
        node.get_logger().info("Moving gear_center")

        # 1. 중앙 기어 잡는 위치로 관절 이동
        movej(
            center_pick_posj,
            radius=0.00,
            ra=DR_MV_RA_DUPLICATE,
            acc=ACC,
            vel=VELOCITY,
        )

        # 2. 그리퍼 잡기
        grip()

        # 3. 들어올리기 (Z=350)
        movel(
            center_posx_list[0],
            radius=0.00,
            ref=0,
            mod=DR_MV_MOD_ABS,
            ra=DR_MV_RA_DUPLICATE,
            acc=ACC,
            vel=VELOCITY,
        )

        # 4. Y축 상대 이동 (-300mm)
        movel(
            rel_move_posx,
            radius=0.00,
            ref=0,
            mod=DR_MV_MOD_REL,
            ra=DR_MV_RA_DUPLICATE,
            acc=ACC,
            vel=VELOCITY,
        )

        # 5. 중앙 기어 안착 위치 접근 (Z=295 -> Z=290)
        for approach_posx in center_posx_list[1:]:
            movel(
                approach_posx,
                radius=0.00,
                ref=0,
                mod=DR_MV_MOD_ABS,
                ra=DR_MV_RA_DUPLICATE,
                acc=ACC,
                vel=VELOCITY,
            )

        # 6. 기어 맞물림 감지 및 주기 회전 모션 후 그리퍼 놓기
        detecting_gear()
        release()

    node.get_logger().info(f"Moving to joint position: {homej}")
    movej(homej, vel=VELOCITY, acc=ACC)

    try:
        for i in range(CYCLE):
            node.get_logger().info(f"=== Cycle {i+1}/{CYCLE} ===")

            gears()
            gear_center()



        node.get_logger().info("Gripper Test Complete")
        

    except KeyboardInterrupt:
        node.get_logger().info("Program Stopped")
    except TimeoutError as e:
        node.get_logger().error(str(e))

    finally:
        try:
            movej(homej, vel=VELOCITY, acc=ACC)
        except Exception as e:
            node.get_logger().error(f"Failed to move home: {e}")

        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()

