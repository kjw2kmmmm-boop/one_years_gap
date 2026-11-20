import math
import rclpy
import DR_init

from icecream_motion_manager.motion_utils import move_axis_sequence
from icecream_motion_manager.pose_config import (
    get_motion_entry,
    get_section_config,
    load_cup_diameter_hit,
)

ROBOT_ID = "dsr01"
ROBOT_MODEL = "m0609"

# =====================================
# 고정 작업 환경 설정 (단위: mm)
# poses.yaml 'cup_hold' 섹션에 동일 키가 있으면 우선 적용된다.
# =====================================

CORNER_XY = (281.49, -230.62)   # 측정판 모서리 (cup_corner_push / cup_diameter_calibration)
GROUND_Z = 9.0               # 컵 바닥 Z (cup_calibration.ground_z)

X_SIGN = 1                    # 모서리 기준 컵이 놓이는 X 방향
Y_SIGN = 1                    # 모서리 기준 컵이 놓이는 Y 방향

GRIP_DEPTH = 0             # 컵 입구에서 아래로 잡는 깊이
HIT_OFFSET_XY = (0.0, 0.0)  # 지름 측정 접촉 좌표(X, Y) 기준 파지 보정 오프셋 (mm)
TCP_OFFSET = (0.0, 0.0, 238.0)  # closed_floor_z(238.0) / -tip_offset_z(238.0) 기준 보정값

SAFE_Z = 410.0                # 수평 이동 안전 높이 (cup_corner_push / cup_diameter_calibration.safe_z)

HEIGHT_RANGE = (30.0, 175.0)  # min_z(30.0) ~ SAFE_Z(410) 미만 파지 가능 높이
DIAMETER_RANGE = (40.0, 150.0)  # 컵 지름 허용 규격 범위


def _resolve_hold_settings() -> dict:
    """모듈 기본값과 poses.yaml의 cup_hold 설정을 병합한다."""
    try:
        cfg = get_section_config("cup_hold")
    except Exception:
        cfg = {}

    return {
        "corner_xy": cfg.get("corner_xy", CORNER_XY),
        "ground_z": float(cfg.get("ground_z", GROUND_Z)),
        "x_sign": int(cfg.get("x_sign", X_SIGN)),
        "y_sign": int(cfg.get("y_sign", Y_SIGN)),
        "grip_depth": float(cfg.get("grip_depth", GRIP_DEPTH)),
        "hit_offset_xy": cfg.get("hit_offset_xy", HIT_OFFSET_XY),
        "tcp_offset": cfg.get("tcp_offset", TCP_OFFSET),
        "safe_z": cfg.get("safe_z", SAFE_Z),
        "height_range": cfg.get("height_range", HEIGHT_RANGE),
        "diameter_range": cfg.get("diameter_range", DIAMETER_RANGE),
    }


# =====================================
# 컵 크기 기반 파지 좌표 이동
# =====================================

def move_cup_hold(cup_height: float | None = None, cup_diameter: float | None = None):
    """측정된 컵 높이·지름(mm)으로 파지 좌표를 계산해 X→Y→Z 순으로 이동한다."""
    import DSR_ROBOT2 as robot

    # 측정 데이터 확인
    if not all(
        v is not None and math.isfinite(v) and v > 0
        for v in (cup_height, cup_diameter)
    ):
        raise RuntimeError("컵 크기 측정 실패")

    settings = _resolve_hold_settings()
    corner_xy = settings["corner_xy"]
    ground_z = settings["ground_z"]
    x_sign = settings["x_sign"]
    y_sign = settings["y_sign"]
    grip_depth = settings["grip_depth"]
    hit_offset_xy = settings["hit_offset_xy"]
    tcp_offset = settings["tcp_offset"]
    safe_z = settings["safe_z"]
    height_range = settings["height_range"]
    diameter_range = settings["diameter_range"]

    if any(
        v is None
        for v in (corner_xy, hit_offset_xy, tcp_offset, safe_z, height_range, diameter_range)
    ):
        raise RuntimeError("작업 환경 설정값 입력 필요")

    if len(corner_xy) != 2 or len(hit_offset_xy) != 2 or len(tcp_offset) != 3:
        raise ValueError("corner_xy(2개), hit_offset_xy(2개), tcp_offset(3개) 형식이 올바르지 않습니다.")
    if len(height_range) != 2 or len(diameter_range) != 2:
        raise ValueError("height_range(2개), diameter_range(2개) 형식이 올바르지 않습니다.")

    safe_z = float(safe_z)
    if not float(height_range[0]) <= cup_height <= float(height_range[1]):
        raise RuntimeError("허용 컵 높이 범위 초과")

    if not float(diameter_range[0]) <= cup_diameter <= float(diameter_range[1]):
        raise RuntimeError("허용 컵 지름 범위 초과")

    if cup_height <= grip_depth:
        raise RuntimeError("컵 높이 부족")

    # 1. 기존 YAML 좌표, 속도, 가속도 불러오기
    target_pos, vel, acc = get_motion_entry("cup_hold")
    target_pos = list(target_pos)

    # 2. 컵의 반지름 및 Z 계산
    cup_radius = cup_diameter / 2.0
    cup_z = ground_z + cup_height
    grip_z = cup_z - grip_depth
    target_pos[2] = grip_z + float(tcp_offset[2])

    # 3. 실측 접촉 좌표가 저장되어 있고 지름이 일치하면 (-5mm, -5mm) 보정 우선 사용, 없으면 corner_xy 계산 fallback
    saved_hit = load_cup_diameter_hit()
    use_saved_hit = (
        saved_hit is not None
        and (
            saved_hit.get("diameter") is None
            or abs(float(saved_hit["diameter"]) - float(cup_diameter)) <= 0.5
        )
    )

    cup_x: float | None = None
    cup_y: float | None = None
    if use_saved_hit and saved_hit is not None:
        hit_pos = saved_hit["hit_pos"]
        hit_x, hit_y = float(hit_pos[0]), float(hit_pos[1])
        target_pos[0] = hit_x + float(hit_offset_xy[0])
        target_pos[1] = hit_y + float(hit_offset_xy[1])
    else:
        cup_x = float(corner_xy[0]) + x_sign * cup_radius
        cup_y = float(corner_xy[1]) + y_sign * cup_radius
        grip_x = cup_x + x_sign * cup_radius
        grip_y = cup_y
        target_pos[0] = grip_x + float(tcp_offset[0])
        target_pos[1] = grip_y + float(tcp_offset[1])

    # 6. 안전한 수평 이동 높이 확인
    current_pos, _sol = robot.get_current_posx(ref=robot.DR_BASE)
    if current_pos is None:
        raise RuntimeError("현재 위치 확인 실패")

    if robot.check_motion() != 0:
        raise RuntimeError("로봇이 이동 중입니다")

    if float(current_pos[2]) < safe_z - 1.0 or target_pos[2] >= safe_z:
        raise RuntimeError("안전 접근 높이 확인 필요")

    # 7. 계산 결과 출력
    print("==============================")
    print(f"컵 높이: {cup_height:.2f}mm")
    print(f"컵 지름: {cup_diameter:.2f}mm")
    print(f"컵 반지름: {cup_radius:.2f}mm")
    if use_saved_hit and saved_hit is not None:
        hit_pos = saved_hit["hit_pos"]
        print(
            f"실측 접촉 기준: ({float(hit_pos[0]):.2f}, {float(hit_pos[1]):.2f})"
            f" + 오프셋 ({float(hit_offset_xy[0]):+.1f}, {float(hit_offset_xy[1]):+.1f})"
        )
    else:
        print(f"컵 중심 X: {cup_x:.2f}")
        print(f"컵 중심 Y: {cup_y:.2f}")
    print(f"파지 X: {target_pos[0]:.2f}")
    print(f"파지 Y: {target_pos[1]:.2f}")
    print(f"파지 Z: {target_pos[2]:.2f}")
    print("==============================")

    # 8. 기존 X → Y → Z 이동 함수 사용
    move_axis_sequence(
        target_pos,
        vel=vel,
        acc=acc,
        label="컵 크기 기반 홀드 위치",
    )

    # 최종 이동 좌표 확인
    actual_pos, _sol = robot.get_current_posx(ref=robot.DR_BASE)
    if actual_pos is None:
        raise RuntimeError("도착 위치 확인 실패")

    if robot.check_motion() != 0 or any(
        abs(float(actual_pos[i]) - target_pos[i]) > 1.0
        for i in range(3)
    ):
        raise RuntimeError("컵 파지 위치 도착 확인 실패")

    print("컵 홀드 위치 이동 완료")
    return target_pos


# =====================================
# 단독 CLI 실행
# =====================================

def main(args=None):
    """단독 CLI 실행용 진입점."""
    rclpy.init(args=args)
    node = None

    try:
        DR_init.__dsr__id = ROBOT_ID
        DR_init.__dsr__model = ROBOT_MODEL

        node = rclpy.create_node("move_cup_hold", namespace=ROBOT_ID)
        DR_init.__dsr__node = node

        # 단독 테스트용 측정 데이터 입력
        cup_height = float(input("컵 높이(mm): "))
        cup_diameter = float(input("컵 지름(mm): "))

        input("이동 경로 안전 확인 후 Enter: ")
        move_cup_hold(cup_height, cup_diameter)
    except Exception as exc:
        print(f"오류 발생: {exc}")
    finally:
        if node is not None:
            node.destroy_node()
        rclpy.try_shutdown()


if __name__ == "__main__":
    main()
