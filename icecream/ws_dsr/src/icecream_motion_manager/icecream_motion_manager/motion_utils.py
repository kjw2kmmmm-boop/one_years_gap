import time

from icecream_motion_manager.pose_config import (
    get_motion_entry,
    get_motion_via,
    get_section_config,
)


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


def move_axis_sequence(
    target_pose: list[float],
    vel: float,
    acc: float,
    label: str = "목표",
    blend_radius: float = 20.0,
    use_blending: bool = False,
) -> None:
    """현재 Z와 목표 Z를 비교해 X→Y→Z 또는 Z 상승→X→Y 순서로 이동한다."""
    import math
    from DSR_ROBOT2 import DR_BASE, DR_MV_MOD_ABS, amovel, get_current_posx, posx

    current_pos, _sol = get_current_posx(ref=DR_BASE)
    if current_pos is None:
        raise RuntimeError("현재 위치 확인 실패")

    cx, cy, cz = float(current_pos[0]), float(current_pos[1]), float(current_pos[2])
    crx, cry, crz = float(current_pos[3]), float(current_pos[4]), float(current_pos[5])
    tx, ty, tz, trx, try_, trz = [float(v) for v in target_pose]

    if cz >= tz:
        raw_waypoints = [
            [tx, cy, cz, trx, try_, trz],
            [tx, ty, cz, trx, try_, trz],
            [tx, ty, tz, trx, try_, trz],
        ]
    else:
        raw_waypoints = [
            [cx, cy, tz, crx, cry, crz],
            [tx, cy, tz, trx, try_, trz],
            [tx, ty, tz, trx, try_, trz],
        ]

    filtered: list[list[float]] = []
    prev_xyz = (cx, cy, cz)
    for idx, wp in enumerate(raw_waypoints):
        is_last = idx == len(raw_waypoints) - 1
        if math.dist(prev_xyz, wp[:3]) >= 1.0 or is_last:
            if is_last and filtered and math.dist(filtered[-1][:3], wp[:3]) < 1.0:
                filtered[-1] = wp
            else:
                filtered.append(wp)
            prev_xyz = (wp[0], wp[1], wp[2])

    if not use_blending or blend_radius <= 0.0 or len(filtered) <= 1:
        for wp in filtered:
            result = amovel(
                posx(*wp),
                vel=vel,
                acc=acc,
                ref=DR_BASE,
                mod=DR_MV_MOD_ABS,
            )
            if result != 0:
                raise RuntimeError(f"{label} 이동 실패")
            wait_for_motion()
        return

    points_with_start = [(cx, cy, cz)] + [tuple(wp[:3]) for wp in filtered]
    blended_waypoints = []
    for idx, wp in enumerate(filtered):
        if idx == len(filtered) - 1:
            radius = 0.0
        else:
            seg_prev = math.dist(points_with_start[idx], points_with_start[idx + 1])
            seg_next = math.dist(points_with_start[idx + 1], points_with_start[idx + 2])
            radius = round(min(float(blend_radius), seg_prev * 0.4, seg_next * 0.4), 2)
        blended_waypoints.append((wp, radius))

    move_blending(
        blended_waypoints,
        vel=vel,
        acc=acc,
        label=label,
    )


def move_blending(
    waypoints: list,
    vel: float,
    acc: float,
    *,
    default_radius: float = 20.0,
    ref: int | None = None,
    mod: int | None = None,
    time_sec: float = 0.0,
    label: str = "경유점 블렌딩",
) -> None:
    """여러 경유점을 블렌딩 반경(radius)으로 부드럽게 이어 이동한 뒤 완료를 대기한다."""
    from DR_common2 import posb, posx
    from DSR_ROBOT2 import DR_BASE, DR_LINE, DR_MV_MOD_ABS, amoveb

    if not waypoints:
        raise ValueError("move_blending 경유점 목록이 비어 있습니다.")
    if float(vel) <= 0.0 or float(acc) <= 0.0:
        raise ValueError("속도(vel)와 가속도(acc)는 0보다 커야 합니다.")
    if float(default_radius) < 0.0:
        raise ValueError("기본 블렌딩 반경(default_radius)은 0 이상이어야 합니다.")

    target_ref = DR_BASE if ref is None else int(ref)
    target_mod = DR_MV_MOD_ABS if mod is None else int(mod)

    seg_list = []
    last_idx = len(waypoints) - 1
    for idx, item in enumerate(waypoints):
        if isinstance(item, posb):
            seg = item
            if idx == last_idx and getattr(seg, "_radius", 0.0) != 0.0:
                seg = posb(seg._seg_type, seg._posx1, seg._posx2, radius=0.0)
            seg_list.append(seg)
            continue

        if (
            isinstance(item, (tuple, list))
            and len(item) == 2
            and isinstance(item[0], (tuple, list))
        ):
            raw_pose, raw_radius = item
            radius = 0.0 if idx == last_idx else float(raw_radius)
        else:
            raw_pose = item
            radius = 0.0 if idx == last_idx else float(default_radius)

        coords = [float(v) for v in raw_pose]
        if len(coords) != 6:
            raise ValueError(f"경유점 좌표는 6개 숫자여야 합니다 (index={idx}).")
        if radius < 0.0:
            raise ValueError(f"블렌딩 반경은 0 이상이어야 합니다 (index={idx}).")

        seg_list.append(posb(DR_LINE, posx(*coords), radius=radius))

    result = amoveb(
        seg_list,
        vel=float(vel),
        acc=float(acc),
        ref=target_ref,
        mod=target_mod,
        time=float(time_sec),
    )
    if result != 0:
        raise RuntimeError(f"{label} 이동 실패")
    wait_for_motion()


def move_to_via(via_section: str = "via_point") -> None:
    """poses.yaml의 경유 포인트 섹션으로 관절 공간 모션(amovej / amovejx) 이동한다."""
    from DSR_ROBOT2 import DR_BASE, amovej, amovejx, get_current_posx, posj, posx

    cfg = get_section_config(via_section)
    vel = float(cfg.get("vel", 60.0))
    acc = float(cfg.get("acc", 60.0))

    if isinstance(cfg.get("joints"), list):
        joints = [float(v) for v in cfg["joints"]]
        if len(joints) != 6:
            raise ValueError(f"poses.yaml '{via_section}.joints'는 6개 숫자 리스트여야 합니다.")
        result = amovej(posj(*joints), vel=vel, acc=acc)
        if result != 0:
            raise RuntimeError(f"경유 포인트({via_section}) 관절 이동 실패")
        wait_for_motion()
        return

    pose = cfg.get("pose")
    if not isinstance(pose, list) or len(pose) != 6:
        raise ValueError(f"poses.yaml '{via_section}.pose'는 6개 숫자 리스트여야 합니다.")
    if "sol" in cfg and cfg["sol"] is not None:

        sol = int(cfg["sol"])
    else:
        _pos, current_sol = get_current_posx(ref=DR_BASE)
        sol = int(current_sol) if isinstance(current_sol, int) and 0 <= current_sol <= 7 else 0

    result = amovejx(
        posx(*[float(v) for v in pose]),
        vel=vel,
        acc=acc,
        ref=DR_BASE,
        sol=sol,
    )
    if result != 0:
        raise RuntimeError(f"경유 포인트({via_section}) 이동 실패")
    wait_for_motion()


def move_section_with_via(
    section: str,
    label: str = "목표",
    pose_key: str = "pose",
    use_blending: bool = False,
) -> None:
    """poses.yaml 섹션에 via가 설정돼 있으면 경유 포인트를 거친 뒤 축 순서대로 이동한다."""
    via_section = get_motion_via(section)
    if via_section:
        move_to_via(via_section)

    target_pos, vel, acc = get_motion_entry(section, pose_key=pose_key)
    cfg = get_section_config(section)
    blend_radius = float(cfg.get("blend_radius", 20.0))
    move_axis_sequence(
        target_pos,
        vel=vel,
        acc=acc,
        label=label,
        blend_radius=blend_radius,
        use_blending=use_blending,
    )


def lift_relative_z(
    distance_mm: float = 150.0,
    vel: float = 80.0,
    acc: float = 80.0,
) -> None:
    """현재 위치에서 Base Z축 방향으로 상대 상승한다."""
    from DSR_ROBOT2 import DR_BASE, DR_MV_MOD_REL, amovel, amoveb, posx

    result = amovel(
        posx(0.0, 0.0, float(distance_mm), 0.0, 0.0, 0.0),
        vel=float(vel),
        acc=float(acc),
        ref=DR_BASE,
        mod=DR_MV_MOD_REL,
    )
    if result != 0:
        raise RuntimeError("Z축 안전 상승 실패")
    wait_for_motion()


DEFAULT_FLANGE_TCP_NAME = "flange_default"


def _resolve_default_tcp_name() -> str:
    """poses.yaml의 robot.default_tcp 설정 또는 기본 플랜지 TCP 이름을 반환한다."""
    try:
        cfg = get_section_config("robot")
        name = str(cfg.get("default_tcp", "")).strip()
        if name:
            return name
    except Exception:
        pass
    return DEFAULT_FLANGE_TCP_NAME


def ensure_default_tcp(default_tcp_name: str | None = None) -> str:
    """활성 TCP가 커스텀 값(예: tcptest)이면 오프셋 0인 기본 플랜지 TCP로 원복한다."""
    from DSR_ROBOT2 import (
        ROBOT_MODE_AUTONOMOUS,
        ROBOT_MODE_MANUAL,
        add_tcp,
        get_robot_mode,
        get_tcp,
        set_robot_mode,
        set_tcp,
    )

    target_tcp = (default_tcp_name or _resolve_default_tcp_name()).strip()
    current_tcp = get_tcp()
    if current_tcp == -1:
        raise RuntimeError("현재 TCP 조회 실패")

    current_name = str(current_tcp).strip()
    if not current_name or current_name == target_tcp:
        return current_name

    prev_mode = get_robot_mode()
    switched_manual = False
    restore_error: RuntimeError | None = None

    try:
        if prev_mode != ROBOT_MODE_MANUAL:
            if set_robot_mode(ROBOT_MODE_MANUAL) != 0:
                raise RuntimeError("TCP 원복을 위한 Manual 모드 전환 실패")
            switched_manual = True

        if set_tcp(target_tcp) != 0:
            if add_tcp(target_tcp, [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]) != 0:
                raise RuntimeError(f"기본 TCP({target_tcp}) 등록 실패")
            if set_tcp(target_tcp) != 0:
                raise RuntimeError(f"기본 TCP({target_tcp}) 설정 실패")
    finally:
        if switched_manual:
            restore_mode = (
                prev_mode
                if prev_mode in (ROBOT_MODE_MANUAL, ROBOT_MODE_AUTONOMOUS)
                else ROBOT_MODE_AUTONOMOUS
            )
            if restore_mode != ROBOT_MODE_MANUAL and set_robot_mode(restore_mode) != 0:
                restore_error = RuntimeError("TCP 원복 후 Auto 모드 복귀 실패")

    if restore_error is not None:
        raise restore_error

    updated_tcp = get_tcp()
    if str(updated_tcp).strip() != target_tcp:
        raise RuntimeError(f"TCP 원복 확인 실패: 현재={updated_tcp!r}")

    print(f"기본 TCP({target_tcp})로 원복 완료 (이전: {current_name})")
    return target_tcp
