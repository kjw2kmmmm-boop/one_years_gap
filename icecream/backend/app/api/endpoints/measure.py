import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from schemas.order import MeasureRequest, MeasureResultResponse
from services.order_service import order_service

measure = APIRouter(tags=["measure"])


@measure.get(
    "/measure",
    response_model=MeasureResultResponse,
    status_code=status.HTTP_200_OK,
    description="최근 측정된 컵 크기 조회",
)
async def get_measure() -> MeasureResultResponse:
    return order_service.get_latest_measure()


@measure.post(
    "/measure",
    response_model=MeasureResultResponse,
    status_code=status.HTTP_200_OK,
    description="컵 측정 실행 (order_manage /measure_cup)",
)
async def run_measure(payload: MeasureRequest | None = None) -> MeasureResultResponse:
    req = payload or MeasureRequest()
    return await order_service.measure_cup(
        measure_diameter=req.measure_diameter,
        expected_diameter=req.expected_diameter,
    )


@measure.websocket("/ws/measuring")
async def measure_cup(websocket: WebSocket) -> None:
    """컵 측정 실행 및 실시간 진행 단계 스트리밍 WebSocket."""
    await websocket.accept()
    measure_diameter = True
    expected_diameter = 90.0

    try:
        try:
            raw = await asyncio.wait_for(websocket.receive_text(), timeout=0.5)
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                measure_diameter = bool(parsed.get("measure_diameter", False))
                expected_diameter = float(parsed.get("expected_diameter", 90.0))
        except (asyncio.TimeoutError, ValueError, TypeError, json.JSONDecodeError):
            pass

        measure_task = asyncio.create_task(
            order_service.measure_cup(
                measure_diameter=measure_diameter,
                expected_diameter=expected_diameter,
                websocket=websocket,
            )
        )

        # 클라이언트가 연결을 끊거나 종료할 때 측정 태스크도 즉시 취소할 수 있도록 감시한다.
        async def _watch_disconnect() -> None:
            while not measure_task.done():
                await websocket.receive_text()

        watch_task = asyncio.create_task(_watch_disconnect())
        try:
            await measure_task
        finally:
            watch_task.cancel()
            try:
                await watch_task
            except (asyncio.CancelledError, WebSocketDisconnect):
                pass

        await websocket.close()
    except WebSocketDisconnect:
        if "measure_task" in locals() and not measure_task.done():
            measure_task.cancel()
            try:
                await measure_task
            except asyncio.CancelledError:
                pass
