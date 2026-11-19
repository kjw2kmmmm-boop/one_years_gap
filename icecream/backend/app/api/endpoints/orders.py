from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect, status

from schemas.order import OrderCreateRequest, OrderResponse
from services.order_service import order_service

order = APIRouter(tags=["orders"])


@order.get(
    "/orders",
    response_model=list[OrderResponse],
    status_code=status.HTTP_200_OK,
    description="대시보드용 주문내역 조회",
)
def get_orders(
    limit: int = Query(default=50, ge=1, le=200),
    order_status: str | None = Query(default=None, alias="status"),
) -> list[OrderResponse]:
    """SQLite에 저장된 주문 내역 목록을 최신순으로 반환한다."""
    rows = order_service.list_orders(limit=limit, status=order_status)
    return [OrderResponse.model_validate(row) for row in rows]


@order.get(
    "/orders/{order_code}",
    response_model=OrderResponse,
    status_code=status.HTTP_200_OK,
    description="주문 상세 조회",
)
def get_order_detail(order_code: str) -> OrderResponse:
    row = order_service.get_order(order_code)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"주문을 찾을 수 없습니다: {order_code}",
        )
    return OrderResponse.model_validate(row)


@order.post(
    "/order",
    response_model=OrderResponse,
    status_code=status.HTTP_201_CREATED,
    description="키오스크 주문 생성 및 제조 시작",
)
async def push_order(payload: OrderCreateRequest) -> OrderResponse:
    """주문을 DB에 저장하고 order_manage 액션 실행을 시작한다."""
    row = order_service.create_order(payload)
    return OrderResponse.model_validate(row)


async def _handle_order_ws(order_code: str, websocket: WebSocket) -> None:
    await order_service.subscribe_order_progress(order_code, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        order_service.disconnect_order_progress(order_code, websocket)


@order.websocket("/ws/order-progress/{order_code}")
async def progress_order_by_path(websocket: WebSocket, order_code: str) -> None:
    """주문 코드별 제조 진행률 스트리밍 WebSocket."""
    await _handle_order_ws(order_code, websocket)


@order.websocket("/ws/order-progress")
async def progress_order(
    websocket: WebSocket,
    order_code: str = Query(..., min_length=1),
) -> None:
    """쿼리 파라미터(order_code) 기반 제조 진행률 스트리밍 WebSocket."""
    await _handle_order_ws(order_code, websocket)
