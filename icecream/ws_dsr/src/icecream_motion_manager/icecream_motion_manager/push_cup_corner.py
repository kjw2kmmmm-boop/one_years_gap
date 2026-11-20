import math
import statistics
import time

import DR_init
import rclpy

from icecream_motion_manager.gripper import griper_release, griper_cup
from icecream_motion_manager.smooth_controller import (
    DEFAULT_WORKSPACE_CONSTANTS,
    ROBOT_ID,
    ROBOT_MODEL,
    SYSTEM_HOME,
    SmoothController,
    grid_to_xy,
    load_section_params,
)

DEFAULT_PUSH_CUP_CORNER_PARAMS = {
    **DEFAULT_WORKSPACE_CONSTANTS,
    "cup_start_gx": 0.75,
    "cup_start_gy": 0.75,
    "low_drag_z": 190.0,
    "offset_dist": 125.0,
    "pre_stop_dist": 170.0,
    "end_dist": 95.0,
    "retreat_dist": 45.0,
    "push_speed": 15.0,
    "push_acc": 10.0,
    "retreat_speed": 15.0,
    "retreat_acc": 15.0,
    "push_force_threshold": 1.8,
}


def push_cup_corner(node=None) -> str:
    """외력 감지로 컵을 코너 벽까지 스무스하게 밀착시킨 뒤 복귀한다."""
    if node is None:
        node = DR_init.__dsr__node
    if node is None:
        raise RuntimeError("DR_init.__dsr__node가 초기화되지 않았습니다.")

    from DR_common2 import posj, posx
    from DSR_ROBOT2 import DR_BASE, movej, movel, wait

    params = load_section_params("cup_corner_push", DEFAULT_PUSH_CUP_CORNER_PARAMS)
    vel_j = params["vel_j"]
    acc_j = params["acc_j"]
    vel_x = params["vel_x"]
    acc_x = params["acc_x"]
    safe_z = params["safe_z"]
    corner_x = params["corner_x"]
    corner_y = params["corner_y"]
    grid_step_mm = params["grid_step_mm"]
    abort_force = params["abort_force"]
    hits_required = int(params["hits_required"])
    sample_sleep = params["sample_sleep"]

    cup_start_gx = params["cup_start_gx"]
    cup_start_gy = params["cup_start_gy"]
    low_drag_z = params["low_drag_z"]
    offset_dist = params["offset_dist"]
    pre_stop_dist = params["pre_stop_dist"]
    end_dist = params["end_dist"]
    retreat_dist = params["retreat_dist"]
    push_speed = params["push_speed"]
    push_acc = params["push_acc"]
    retreat_speed = params["retreat_speed"]
    retreat_acc = params["retreat_acc"]
    push_force_threshold = params["push_force_threshold"]

    start_x, start_y = grid_to_xy(
        cup_start_gx,
        cup_start_gy,
        corner_x=corner_x,
        corner_y=corner_y,
        step_mm=grid_step_mm,
    )
    node.get_logger().info(f"▶ [1단계] ({cup_start_gx}, {cup_start_gy}) 컵 스무스 밀착 시작")

    with SmoothController(node, sample_sleep=sample_sleep) as ctrl:
        movej(posj(SYSTEM_HOME), vel=vel_j, acc=acc_j)
        griper_cup()

        #movej(posj([0.0, 0.0, 90.0, 45.0, 75.0, 90.0]), vel=vel_j, acc=acc_j)
        #wait(0.5)

        drag_a, drag_b, drag_c = 45.0, -165.0, 90.0

        dx = corner_x - start_x
        dy = corner_y - start_y
        dist = math.hypot(dx, dy)
        ux, uy = dx / dist, dy / dist
        u_diag = math.sqrt(0.5)

        entry_x = round(start_x - (ux * offset_dist), 2)
        entry_y = round(start_y - (uy * offset_dist), 2)

        #드래그할 위치 이동
        #movel(posx([entry_x, entry_y, safe_z, drag_a, drag_b, drag_c]), vel=vel_x, acc=acc_x, ref=DR_BASE)
        movel(posx([entry_x, entry_y, low_drag_z, drag_a, drag_b, drag_c]), vel=50, acc=50, ref=DR_BASE)
        #wait()

        pre_x = round(corner_x + (pre_stop_dist * u_diag), 2)
        pre_y = round(corner_y + (pre_stop_dist * u_diag), 2)

        # 드래그 하면서 지름 측정 시작
        movel(posx([pre_x, pre_y, low_drag_z, drag_a, drag_b, drag_c]), vel=40, acc=50, ref=DR_BASE)
        time.sleep(0.2)

        base_fx, base_fy, _ = ctrl.read_baseline()

        target = [
            round(corner_x + (end_dist * u_diag), 2),
            round(corner_y + (end_dist * u_diag), 2),
            low_drag_z,
            drag_a,
            drag_b,
            drag_c,
        ]

        ctrl.start_move(target, push_speed, push_acc)

        hits = 0
        moving_samples = []
        moving_base = None
        start_pos = [pre_x, pre_y]
        stopped_pose = target
        stop_reason = "목표 거리 도달"

        try:
            for here, f in ctrl.monitor_motion(target):
                traveled = math.hypot(here[0] - start_pos[0], here[1] - start_pos[1])
                load = math.hypot(f[0] - base_fx, f[1] - base_fy)

                if load >= abort_force:
                    stopped_pose = ctrl.stop()
                    stop_reason = f"과부하 즉시 정지 ({load:.2f}N)"
                    node.get_logger().warn(f"  ⚠️ {stop_reason}")
                    break

                if moving_base is None:
                    if 3.0 <= traveled < 8.0:
                        moving_samples.append((f[0], f[1]))
                    elif traveled >= 8.0:
                        if len(moving_samples) >= 2:
                            moving_base = (
                                statistics.median(s[0] for s in moving_samples),
                                statistics.median(s[1] for s in moving_samples),
                            )
                        else:
                            moving_base = (base_fx, base_fy)

                ref_fx, ref_fy = moving_base if moving_base is not None else (base_fx, base_fy)
                delta_fxy = math.hypot(f[0] - ref_fx, f[1] - ref_fy)

                if traveled > 8.0 and delta_fxy >= push_force_threshold:
                    hits += 1
                    if hits >= hits_required:
                        stopped_pose = ctrl.stop()
                        stop_reason = f"벽 접촉 정지 (ΔFxy={delta_fxy:.2f}N)"
                        node.get_logger().info(f"  --> 🎯 {stop_reason}")
                        break
                else:
                    hits = 0
        except Exception:
            try:
                ctrl.stop()
            except Exception:
                pass
            raise

        retreat_x = round(stopped_pose[0] - (ux * retreat_dist), 2)
        retreat_y = round(stopped_pose[1] - (uy * retreat_dist), 2)

        movel(
            posx([retreat_x, retreat_y, low_drag_z, drag_a, drag_b, drag_c]),
            vel=retreat_speed,
            acc=retreat_acc,
            ref=DR_BASE,
        )
        movel(
            posx([retreat_x, retreat_y, safe_z, drag_a, drag_b, drag_c]),
            vel=vel_x,
            acc=acc_x,
            ref=DR_BASE,
        )

    result_msg = f"컵 코너 밀착 완료 ({stop_reason})"
    node.get_logger().info(f"▶ [1단계 완료] {result_msg}")
    return result_msg


def main(args=None) -> None:
    """단독 CLI 실행용 진입점."""
    rclpy.init(args=args)
    node = None

    try:
        DR_init.__dsr__id = ROBOT_ID
        DR_init.__dsr__model = ROBOT_MODEL

        node = rclpy.create_node("push_cup_corner", namespace=ROBOT_ID)
        DR_init.__dsr__node = node

        input("컵 코너 밀착 경로 안전 확인 후 Enter: ")
        print(push_cup_corner(node=node))
    except Exception as exc:
        print(f"오류 발생: {exc}")
    finally:
        if node is not None:
            node.destroy_node()
        rclpy.try_shutdown()


if __name__ == "__main__":
    main()
