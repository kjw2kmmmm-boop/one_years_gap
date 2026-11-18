from collections.abc import Awaitable, Callable

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, status

from schemas.dashboard import MoveToFlavorRequest, TaskExecuteResponse, TelemetrySnapshot
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
    "/calibrate-cup-z",
    response_model=TaskExecuteResponse,
    status_code=status.HTTP_200_OK,
    description="컵 높이(Z) 접촉 측정 캘리브레이션",
)
async def calibrate_cup_z_height() -> TaskExecuteResponse:
    """대시보드에서 측정판 하강 접촉 감지로 컵 높이를 측정한다."""
    return await _run(dashboard_service.calibrate_cup_z)


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
