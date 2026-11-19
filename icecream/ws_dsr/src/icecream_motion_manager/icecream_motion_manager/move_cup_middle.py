import rclpy
import DR_init

from icecream_motion_manager.motion_utils import wait_for_motion
from icecream_motion_manager.pose_config import get_motion_entry, get_section_config

ROBOT_ID = "dsr01"
ROBOT_MODEL = "m0609"


def move_cup_middle():
    """그립한 컵을 cup_middle(rel_pose) 위치로 이동한 뒤 Tool 좌표계 기준 Ry를 +10도 회전한다."""
    from DSR_ROBOT2 import DR_BASE, DR_MV_MOD_ABS, DR_MV_MOD_REL, DR_TOOL, amovel, get_current_posx, posx

    rel_pose, vel, acc = get_motion_entry("cup_middle", pose_key="rel_pose")
    cfg = get_section_config("cup_middle")
    tool_rel_pose = [float(v) for v in cfg.get("tool_rel_pose", [0.0, 0.0, 0.0, 0.0, 10.0, 0.0])]
    if len(tool_rel_pose) != 6:
        raise ValueError("poses.yaml 'cup_middle.tool_rel_pose'는 6개 숫자 리스트여야 합니다.")

    current, _sol = get_current_posx(ref=DR_BASE)
    if current is None:
        raise RuntimeError("현재 위치 확인 실패")

    target = posx(*[float(c) + float(d) for c, d in zip(current[:6], rel_pose)])

    result = amovel(
        target,
        vel=vel,
        acc=acc,
        ref=DR_BASE,
        mod=DR_MV_MOD_ABS,
    )
    if result != 0:
        raise RuntimeError("컵 중간 위치(spiral) 이동 실패")
    wait_for_motion()

    if any(abs(v) > 1e-6 for v in tool_rel_pose):
        rot_result = amovel(
            posx(*tool_rel_pose),
            vel=vel,
            acc=acc,
            ref=DR_TOOL,
            mod=DR_MV_MOD_REL,
        )
        if rot_result != 0:
            raise RuntimeError("컵 중간 위치 Tool Ry 회전 실패")
        wait_for_motion()

    print("컵 중간 위치 이동 및 Tool Ry 회전 완료")


def main(args=None):
    """단독 CLI 실행용 진입점."""
    rclpy.init(args=args)
    node = None

    try:
        DR_init.__dsr__id = ROBOT_ID
        DR_init.__dsr__model = ROBOT_MODEL

        node = rclpy.create_node("cup_lift", namespace=ROBOT_ID)
        DR_init.__dsr__node = node

        input("이동 경로 안전 확인 후 Enter: ")
        move_cup_middle()
    except Exception as exc:
        print(f"오류 발생: {exc}")
    finally:
        if node is not None:
            node.destroy_node()
        rclpy.try_shutdown()


if __name__ == "__main__":
    main()
