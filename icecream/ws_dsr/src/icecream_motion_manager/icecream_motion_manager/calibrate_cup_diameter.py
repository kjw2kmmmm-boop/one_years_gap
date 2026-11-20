import math
import statistics
import time

import DR_init
import rclpy

from icecream_motion_manager.gripper import griper_grap
from icecream_motion_manager.pose_config import (
    clear_cup_diameter_hit,
    save_cup_diameter_hit,
)
from icecream_motion_manager.smooth_controller import (
    DEFAULT_WORKSPACE_CONSTANTS,
    ROBOT_ID,
    ROBOT_MODEL,
    SYSTEM_HOME,
    SmoothController,
    load_section_params,
)

DEFAULT_CALIBRATE_CUP_DIAMETER_PARAMS = {
    **DEFAULT_WORKSPACE_CONSTANTS,
    "diag_j6": 45.0,
    "side_probe_z": 335.0,
    "closed_floor_z": 238.0,
    "probe_below_top_mm": 20.0,
    "min_side_probe_z": 255.0,
    "start_dist": 165.0,
    "end_dist": 65.0,
    "probe_speed": 4.0,
    "probe_acc": 8.0,
    "xy_force_threshold": 1.5,
    "gripper_half_thick": 7.0,
    "fallback_radius": 47.5,
    "fallback_diameter": 95.0,
}



def resolve_side_probe_z(
    params: dict[str, float],
    cup_height_mm: float | None = None,
) -> float:
    """측정된 컵 높이(mm)를 TCP Z(mm)로 변환하고 안전 범위로 클램프한다."""
    safe_z = params["safe_z"]
    min_z = params["min_side_probe_z"] + 20.0
    max_z = safe_z #+ 10.0

    if cup_height_mm is not None and cup_height_mm > 0.0:
        raw_z = params["closed_floor_z"] + float(cup_height_mm) - params["probe_below_top_mm"]
    else:
        raw_z = params["side_probe_z"]

    return round(max(min_z, min(raw_z, max_z)), 2)


def calibrate_cup_diameter(
    node=None,
    cup_height_mm: float | None = None,
    *,
    allow_fallback: bool = True,
) -> tuple[float, float] | None:
    """코너에 밀착된 컵의 측면 접촉 감지로 반지름·지름(mm)을 실측한다."""
    if node is None:
        node = DR_init.__dsr__node
    if node is None:
        raise RuntimeError("DR_init.__dsr__node가 초기화되지 않았습니다.")

    from DR_common2 import posj, posx
    from DSR_ROBOT2 import DR_BASE, movej, movel

    params = load_section_params(
        "cup_diameter_calibration",
        DEFAULT_CALIBRATE_CUP_DIAMETER_PARAMS,
    )
    vel_j = params["vel_j"]
    acc_j = params["acc_j"]
    vel_x = params["vel_x"]
    acc_x = params["acc_x"]
    safe_z = params["safe_z"]
    corner_x = params["corner_x"]
    corner_y = params["corner_y"]
    abort_force = params["abort_force"]
    hits_required = int(params["hits_required"])
    sample_sleep = params["sample_sleep"]

    diag_j6 = params["diag_j6"]
    diag_c = diag_j6
    side_probe_z = resolve_side_probe_z(params, cup_height_mm=cup_height_mm)
    start_dist = params["start_dist"]
    end_dist = params["end_dist"]
    probe_speed = params["probe_speed"]
    probe_acc = params["probe_acc"]
    xy_force_threshold = params["xy_force_threshold"]
    gripper_half_thick = params["gripper_half_thick"]
    fallback_radius = params["fallback_radius"]
    fallback_diameter = params["fallback_diameter"]

    if cup_height_mm is not None and cup_height_mm > 0.0:
        node.get_logger().info(
            f"▶ [2단계] 컵 지름 스무스 실측 시작 (컵 높이 {cup_height_mm:.1f}mm → probe Z={side_probe_z:.2f}mm)"
        )
    else:
        node.get_logger().info(
            f"▶ [2단계] 컵 지름 스무스 실측 시작 (기본 probe Z={side_probe_z:.2f}mm)"
        )

    with SmoothController(node, sample_sleep=sample_sleep) as ctrl:
        #movej(posj(SYSTEM_HOME), vel=vel_j, acc=acc_j)
        griper_grap()

        #movej(posj([0.0, 0.0, 90.0, 0.0, 90.0, diag_j6]), vel=vel_j, acc=acc_j)

        u_diag = math.sqrt(0.5)
        start_x = round(corner_x + (start_dist * u_diag), 2)
        start_y = round(corner_y + (start_dist * u_diag), 2)

        start_x = round(corner_x + (start_dist * u_diag), 2)
        start_y = round(corner_y + (start_dist * u_diag), 2)
        
        target = [
            round(corner_x + (end_dist * u_diag), 2),
            round(corner_y + (end_dist * u_diag), 2),
            side_probe_z,
            0.0,
            -180.0,
            diag_c,
        ]

        movel(posx([start_x, start_y, safe_z, 0.0, -180.0, diag_c]), vel=vel_x, acc=acc_x, ref=DR_BASE)
        movel(posx([start_x, start_y, side_probe_z, 0.0, -180.0, diag_c]), vel=50, acc=50, ref=DR_BASE)
        time.sleep(0.2)

        rest_fx, rest_fy, _ = ctrl.read_baseline()

        ctrl.start_move(target, probe_speed, probe_acc)

        samples = []
        baseline = None
        hits = 0
        first_hit = None
        hit_pose: list[float] | None = None
        contact_dist = None

        try:
            for here, f in ctrl.monitor_motion(target):
                traveled = math.hypot(here[0] - start_x, here[1] - start_y)

                if baseline is None:
                    if 2.0 <= traveled < 6.0:
                        samples.append((f[0], f[1]))
                    elif traveled >= 6.0:
                        if len(samples) >= 2:
                            baseline = (
                                statistics.median(s[0] for s in samples),
                                statistics.median(s[1] for s in samples),
                            )
                        else:
                            baseline = (rest_fx, rest_fy)

                ref_fx, ref_fy = baseline if baseline is not None else (rest_fx, rest_fy)
                delta = math.hypot(f[0] - ref_fx, f[1] - ref_fy)

                if delta >= abort_force:
                    ctrl.stop()
                    node.get_logger().warn(f"  ⚠️ 지름 측정 중 과부하 정지 ({delta:.2f}N)")
                    break

                if traveled >= 6.0 and delta >= xy_force_threshold:
                    if hits == 0:
                        first_hit = list(here)
                    hits += 1
                    if hits >= hits_required:
                        ctrl.stop()
                        hit_pos = first_hit if first_hit is not None else here
                        hit_pose = [float(v) for v in hit_pos]
                        contact_dist = round(math.hypot(hit_pos[0] - corner_x, hit_pos[1] - corner_y), 2)
                        node.get_logger().info(f"  --> 🎯 측면 스무스 터치! L = {contact_dist} mm (ΔFxy={delta:.2f}N)")
                        break
                else:
                    hits = 0
                    first_hit = None
        except Exception:
            try:
                ctrl.stop()
            except Exception:
                pass
            raise

        movel(posx([start_x, start_y, side_probe_z, 0.0, -180.0, diag_c]), vel=40, acc=60, ref=DR_BASE)
        movel(posx([start_x, start_y, safe_z, 0.0, -180.0, diag_c]), vel=vel_x, acc=acc_x, ref=DR_BASE)

    if contact_dist is not None:
        effective_l = contact_dist - gripper_half_thick
        radius = round(effective_l / (math.sqrt(2.0) + 1.0), 1)
        diameter = round(radius * 2.0, 1)
        if hit_pose is not None:
            saved_path = save_cup_diameter_hit(
                hit_pose,
                diameter=diameter,
                radius=radius,
                cup_height_mm=cup_height_mm,
            )
            node.get_logger().info(
                f"▶ [접촉 좌표 저장] X={hit_pose[0]:.2f}, Y={hit_pose[1]:.2f} → {saved_path}"
            )
    elif allow_fallback:
        clear_cup_diameter_hit()
        radius = fallback_radius
        diameter = fallback_diameter
    else:
        clear_cup_diameter_hit()
        node.get_logger().warn("▶ [2단계 중단] 컵 측면 접촉이 감지되지 않았습니다.")
        return None

    node.get_logger().info(f"▶ [2단계 완료] 지름: {diameter} mm (반지름: {radius} mm)")
    return radius, diameter


def main(args=None) -> None:
    """단독 CLI 실행용 진입점."""
    rclpy.init(args=args)
    node = None

    try:
        DR_init.__dsr__id = ROBOT_ID
        DR_init.__dsr__model = ROBOT_MODEL

        node = rclpy.create_node("calibrate_cup_diameter", namespace=ROBOT_ID)
        DR_init.__dsr__node = node

        input("컵 지름 측정 경로 안전 확인 후 Enter: ")
        radius, diameter = calibrate_cup_diameter(node=node)
        print(f"컵 지름 측정 완료: {diameter:.1f}mm (반지름 {radius:.1f}mm)")
    except Exception as exc:
        print(f"오류 발생: {exc}")
    finally:
        if node is not None:
            node.destroy_node()
        rclpy.try_shutdown()


if __name__ == "__main__":
    main()
