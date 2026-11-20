from collections.abc import Awaitable, Callable

from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect, status

from schemas.dashboard import (
    ActionLogResponse,
    MoveToFlavorRequest,
    TaskExecuteResponse,
    TelemetrySnapshot,
)
from services.dashboard_service import DashboardServiceError, dashboard_service
from services.telemetry_service import telemetry_service

dashboard = APIRouter(tags=["dashboard"])


async def _run(action: Callable[[], Awaitable[TaskExecuteResponse]]) -> TaskExecuteResponse:
    try:
        return await action()
    except DashboardServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


@dashboard.post(
    "/home",
    response_model=TaskExecuteResponse,
    status_code=status.HTTP_200_OK,
    description="로봇 HOME 이동 및 그리퍼 열기",
)
async def move_robot_home() -> TaskExecuteResponse:
    """대시보드에서 로봇을 HOME 위치로 이동시키고 그리퍼를 연다."""
    return await _run(dashboard_service.move_home)


@dashboard.post(
    "/move-to-scoop",
    response_model=TaskExecuteResponse,
    status_code=status.HTTP_200_OK,
    description="스쿠프 위치로 이동",
)
async def move_robot_to_scoop() -> TaskExecuteResponse:
    """대시보드에서 로봇을 스쿠프 위치로 이동시킨다."""
    return await _run(dashboard_service.move_to_scoop)


@dashboard.post(
    "/move-cup-z",
    response_model=TaskExecuteResponse,
    status_code=status.HTTP_200_OK,
    description="컵 측정 위치(Z)로 이동",
)
async def move_robot_cup_z() -> TaskExecuteResponse:
    """대시보드에서 로봇을 컵 측정 위치로 이동시킨다."""
    return await _run(dashboard_service.move_cup_z)


@dashboard.post(
    "/move-cup-hold",
    response_model=TaskExecuteResponse,
    status_code=status.HTTP_200_OK,
    description="컵 홀드 위치로 X→Y→Z 순 이동",
)
async def move_robot_cup_hold() -> TaskExecuteResponse:
    """대시보드에서 로봇을 컵 홀드 위치로 이동시킨다."""
    return await _run(dashboard_service.move_cup_hold)


@dashboard.post(
    "/move-cup-middle",
    response_model=TaskExecuteResponse,
    status_code=status.HTTP_200_OK,
    description="그립한 컵을 spiral 시작 위치로 이동",
)
async def move_robot_cup_middle() -> TaskExecuteResponse:
    """대시보드에서 그립한 컵을 spiral 시작 위치로 이동시킨다."""
    return await _run(dashboard_service.move_cup_middle)


@dashboard.post(
    "/move-cup-sprial",
    response_model=TaskExecuteResponse,
    status_code=status.HTTP_200_OK,
    description="현재 위치에서 컵 나선형 스파이럴 모션 실행",
)
async def move_robot_cup_sprial() -> TaskExecuteResponse:
    """대시보드에서 현재 위치를 기준으로 나선형 스파이럴 모션을 실행한다."""
    return await _run(dashboard_service.move_cup_sprial)


@dashboard.post(
    "/move-to-plate",
    response_model=TaskExecuteResponse,
    status_code=status.HTTP_200_OK,
    description="측정판 손잡이 위치로 이동",
)
async def move_robot_to_plate() -> TaskExecuteResponse:
    """대시보드에서 로봇을 측정판 손잡이 위치로 이동시킨다."""
    return await _run(dashboard_service.move_to_plate)


@dashboard.post(
    "/move-to-flavor",
    response_model=TaskExecuteResponse,
    status_code=status.HTTP_200_OK,
    description="선택한 아이스크림 맛 위치로 이동",
)
async def move_robot_to_flavor(payload: MoveToFlavorRequest) -> TaskExecuteResponse:
    """대시보드에서 지정한 아이스크림 맛 위치로 로봇을 이동시킨다."""
    return await _run(lambda: dashboard_service.move_to_flavor(payload.flavor))


@dashboard.post(
    "/grip-and-lift",
    response_model=TaskExecuteResponse,
    status_code=status.HTTP_200_OK,
    description="그리퍼 닫기 및 Z축 15cm 상승",
)
async def grip_and_lift_robot() -> TaskExecuteResponse:
    """대시보드에서 그리퍼를 닫고 Z축으로 15cm 상승시킨다."""
    return await _run(dashboard_service.grip_and_lift)


@dashboard.post(
    "/gripper-release",
    response_model=TaskExecuteResponse,
    status_code=status.HTTP_200_OK,
    description="그리퍼 열기 (DO2 펄스)",
)
async def release_gripper() -> TaskExecuteResponse:
    """대시보드에서 그리퍼 열기 신호를 출력한다."""
    return await _run(dashboard_service.gripper_release)


@dashboard.post(
    "/gripper-grab",
    response_model=TaskExecuteResponse,
    status_code=status.HTTP_200_OK,
    description="그리퍼 닫기 (DO1 펄스)",
)
async def grab_gripper() -> TaskExecuteResponse:
    """대시보드에서 그리퍼 닫기 신호를 출력한다."""
    return await _run(dashboard_service.gripper_grab)


@dashboard.post(
    "/gripper-cup",
    response_model=TaskExecuteResponse,
    status_code=status.HTTP_200_OK,
    description="컵 파지용 그리퍼 닫기 (DO3 펄스)",
)
async def cup_gripper() -> TaskExecuteResponse:
    """대시보드에서 컵 파지용 그리퍼 닫기(DO3) 신호를 출력한다."""
    return await _run(dashboard_service.gripper_cup)


@dashboard.post(
    "/calibrate-cup-z",
    response_model=TaskExecuteResponse,
    status_code=status.HTTP_200_OK,
    description="컵 높이(Z) 접촉 측정 캘리브레이션",
)
async def calibrate_cup_z_height() -> TaskExecuteResponse:
    """대시보드에서 측정판 하강 접촉 감지로 컵 높이를 측정한다."""
    return await _run(dashboard_service.calibrate_cup_z)


@dashboard.post(
    "/push-cup-corner",
    response_model=TaskExecuteResponse,
    status_code=status.HTTP_200_OK,
    description="외력 감지로 컵을 코너 벽까지 스무스 밀착",
)
async def push_cup_to_corner() -> TaskExecuteResponse:
    """대시보드에서 컵을 코너 기준 위치로 밀착시킨다."""
    return await _run(dashboard_service.push_cup_corner)


@dashboard.post(
    "/calibrate-cup-diameter",
    response_model=TaskExecuteResponse,
    status_code=status.HTTP_200_OK,
    description="측면 접촉 감지로 컵 지름 실측 캘리브레이션",
)
async def calibrate_cup_diameter_size() -> TaskExecuteResponse:
    """대시보드에서 측면 접촉 감지로 컵 반지름 및 지름을 실측한다."""
    return await _run(dashboard_service.calibrate_cup_diameter)


@dashboard.post(
    "/scoop-icecream",
    response_model=TaskExecuteResponse,
    status_code=status.HTTP_200_OK,
    description="순응제어·힘 감지 기반 아이스크림 스쿠핑 및 투하 시퀀스 실행",
)
async def run_scoop_icecream() -> TaskExecuteResponse:
    """대시보드에서 아이스크림 스쿠핑(하강·밀기·털기·투하) 전체 모션을 실행한다."""
    return await _run(dashboard_service.scoop_icecream)


@dashboard.post(
    "/flatten-icecream",
    response_model=TaskExecuteResponse,
    status_code=status.HTTP_200_OK,
    description="외력 감지 하강 후 Y축 +200mm 아이스크림 평탄화 시퀀스 실행",
)
async def run_flatten_icecream() -> TaskExecuteResponse:
    """대시보드에서 아이스크림 표면 평탄화(접근·하강·밀기·복귀) 모션을 실행한다."""
    return await _run(dashboard_service.flatten_icecream)


@dashboard.post(
    "/release-scoop",
    response_model=TaskExecuteResponse,
    status_code=status.HTTP_200_OK,
    description="스쿱 거치대 이동·하강·그리퍼 열기·상승 복귀 시퀀스 실행",
)
async def run_release_scoop() -> TaskExecuteResponse:
    """대시보드에서 스쿱을 거치대에 내려놓고 그리퍼를 연 뒤 상승하는 모션을 실행한다."""
    return await _run(dashboard_service.release_scoop)


@dashboard.get(
    "/action-logs",
    response_model=list[ActionLogResponse],
    status_code=status.HTTP_200_OK,
    description="대시보드 실행 이력 조회",
)
async def get_action_logs(
    limit: int = Query(default=50, ge=1, le=200),
    source: str | None = Query(default=None),
) -> list[ActionLogResponse]:
    """SQLite에 저장된 최근 대시보드/모션 실행 이력을 반환한다."""
    rows = dashboard_service.list_action_logs(limit=limit, source=source)
    return [ActionLogResponse.model_validate(row) for row in rows]


@dashboard.delete(
    "/action-logs",
    status_code=status.HTTP_200_OK,
    description="대시보드 실행 이력 삭제",
)
async def clear_action_logs(
    source: str | None = Query(default="DASHBOARD"),
) -> dict[str, int]:
    """저장된 실행 이력을 삭제한다."""
    deleted = dashboard_service.clear_action_logs(source=source)
    return {"deleted": deleted}


@dashboard.get(
    "/telemetry",
    response_model=TelemetrySnapshot,
    status_code=status.HTTP_200_OK,
    description="최신 시스템 텔레메트리 스냅샷 조회",
)
async def get_telemetry() -> TelemetrySnapshot:
    """ROS2 /dashboard/telemetry 토픽에서 수신한 최신 상태를 반환한다."""
    return telemetry_service.get_snapshot()


@dashboard.websocket("/ws/telemetry")
async def telemetry_websocket(websocket: WebSocket) -> None:
    """대시보드에 실시간 텔레메트리를 푸시하는 WebSocket 엔드포인트."""
    await telemetry_service.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        telemetry_service.disconnect(websocket)
