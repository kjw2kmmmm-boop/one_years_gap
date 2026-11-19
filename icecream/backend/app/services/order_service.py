import asyncio
from collections import defaultdict
from datetime import datetime, timezone

from fastapi import WebSocket

from db.database import SessionLocal
from models.order import Order
from repositories.order_repository import order_repository
from ros_bridge.action_client import run_ros_action
from ros_bridge.execute_task_client import RosBridgeError
from schemas.order import MeasureResultResponse, OrderCreateRequest


class OrderService:
    """주문 생성, 컵 측정 및 order_manage Action 실행·진행률 브로드캐스트를 관리한다."""

    def __init__(self) -> None:
        self._order_subscribers: dict[str, set[WebSocket]] = defaultdict(set)
        self._order_tasks: dict[str, asyncio.Task] = {}
        self._latest_measure = MeasureResultResponse(
            success=False,
            message="아직 컵 측정 이력이 없습니다.",
        )

    def list_orders(self, *, limit: int = 50, status: str | None = None) -> list[Order]:
        with SessionLocal() as db:
            return order_repository.list_orders(db, limit=limit, status=status)

    def get_order(self, order_code: str) -> Order | None:
        with SessionLocal() as db:
            return order_repository.get_by_code(db, order_code)

    def get_latest_measure(self) -> MeasureResultResponse:
        return self._latest_measure

    def has_active_order(self) -> bool:
        return bool(self._order_tasks)

    def create_order(self, payload: OrderCreateRequest) -> Order:
        """주문을 SQLite에 PENDING으로 저장하고 백그라운드에서 order_manage 액션을 시작한다."""
        with SessionLocal() as db:
            order = order_repository.create(
                db,
                ice_cream_type=payload.ice_cream_type,
                cup_height_z=payload.cup_height_z,
                cup_diameter=payload.cup_diameter,
                scoops=payload.scoops,
            )

        task = asyncio.create_task(self._run_order_action(order))
        self._order_tasks[order.order_code] = task
        task.add_done_callback(lambda _t, code=order.order_code: self._order_tasks.pop(code, None))
        return order

    async def subscribe_order_progress(self, order_code: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self._order_subscribers[order_code].add(websocket)

        order = self.get_order(order_code)
        if order is not None:
            await websocket.send_json(
                {
                    "type": "snapshot",
                    "order_code": order.order_code,
                    "order_status": order.order_status,
                    "current_step": order.current_step,
                    "progress_percent": order.progress_percent,
                    "error_code": order.error_code,
                    "message": order.error_message or "",
                }
            )
            if order.order_status in {"COMPLETED", "FAILED", "CANCELLED"}:
                await websocket.close()
                self._order_subscribers[order_code].discard(websocket)

    def disconnect_order_progress(self, order_code: str, websocket: WebSocket) -> None:
        subscribers = self._order_subscribers.get(order_code)
        if subscribers is not None:
            subscribers.discard(websocket)
            if not subscribers:
                self._order_subscribers.pop(order_code, None)

    async def _broadcast_order(self, order_code: str, payload: dict, *, close_after: bool = False) -> None:
        clients = list(self._order_subscribers.get(order_code, ()))
        for ws in clients:
            try:
                await ws.send_json(payload)
                if close_after:
                    await ws.close()
            except Exception:
                self.disconnect_order_progress(order_code, ws)
        if close_after:
            self._order_subscribers.pop(order_code, None)

    async def _run_order_action(self, order: Order) -> None:
        code = order.order_code
        with SessionLocal() as db:
            order_repository.mark_started(db, code, current_step="DISPATCHING")

        await self._broadcast_order(
            code,
            {
                "type": "feedback",
                "order_code": code,
                "order_status": "IN_PROGRESS",
                "current_step": "DISPATCHING",
                "current_scoop_index": 0,
                "progress_percent": 0.0,
                "message": "order_manage 노드로 주문을 전달하는 중입니다.",
            },
        )

        async def _on_event(event: dict) -> None:
            if event.get("type") != "feedback":
                return
            order_status = str(event.get("order_status") or "IN_PROGRESS")
            current_step = str(event.get("current_step") or "")
            progress = float(event.get("progress_percent") or 0.0)
            with SessionLocal() as db:
                order_repository.update_progress(
                    db,
                    code,
                    order_status=order_status,
                    current_step=current_step,
                    progress_percent=progress,
                )
            await self._broadcast_order(code, {"order_code": code, **event})

        try:
            result = await run_ros_action(
                action_type="execute_order",
                action_name="/execute_order",
                goal_payload={
                    "order_code": order.order_code,
                    "ice_cream_type": order.ice_cream_type,
                    "cup_height_z": order.cup_height_z or 0.0,
                    "cup_diameter": order.cup_diameter or 0.0,
                    "scoops": order.scoops,
                },
                on_event=_on_event,
                call_timeout=300.0,
            )
        except RosBridgeError as exc:
            with SessionLocal() as db:
                order_repository.mark_failed(
                    db,
                    code,
                    error_code=1,
                    error_message=str(exc),
                )
            await self._broadcast_order(
                code,
                {
                    "type": "result",
                    "order_code": code,
                    "order_status": "FAILED",
                    "success": False,
                    "error_code": 1,
                    "progress_percent": 0.0,
                    "message": str(exc),
                },
                close_after=True,
            )
            return

        if result.get("success"):
            with SessionLocal() as db:
                order_repository.mark_completed(db, code)
            await self._broadcast_order(
                code,
                {
                    "type": "result",
                    "order_code": code,
                    "order_status": "COMPLETED",
                    "success": True,
                    "error_code": 0,
                    "progress_percent": 100.0,
                    "message": str(result.get("message") or "제조 완료"),
                },
                close_after=True,
            )
        else:
            err_code = int(result.get("error_code") or 1)
            err_msg = str(result.get("message") or "주문 제조에 실패했습니다.")
            with SessionLocal() as db:
                order_repository.mark_failed(
                    db,
                    code,
                    error_code=err_code,
                    error_message=err_msg,
                )
            await self._broadcast_order(
                code,
                {
                    "type": "result",
                    "order_code": code,
                    "order_status": "FAILED",
                    "success": False,
                    "error_code": err_code,
                    "message": err_msg,
                },
                close_after=True,
            )

    async def measure_cup(
        self,
        *,
        measure_diameter: bool = True,
        expected_diameter: float = 90.0,
        websocket: WebSocket | None = None,
    ) -> MeasureResultResponse:
        """order_manage(/measure_cup) 액션을 호출하고 선택적으로 WebSocket에 진행률을 스트리밍한다."""

        async def _on_event(event: dict) -> None:
            if websocket is not None and event.get("type") == "feedback":
                await websocket.send_json(event)

        try:
            result = await run_ros_action(
                action_type="measure_cup",
                action_name="/measure_cup",
                goal_payload={
                    "measure_diameter": measure_diameter,
                    "expected_diameter": expected_diameter,
                },
                on_event=_on_event,
                call_timeout=300.0,
            )
        except RosBridgeError as exc:
            response = MeasureResultResponse(
                success=False,
                cup_available=False,
                error_code=1,
                message=str(exc),
                measured_at=datetime.now(timezone.utc),
            )
            self._latest_measure = response
            if websocket is not None:
                await websocket.send_json({"type": "result", **response.model_dump(mode="json")})
            return response

        response = MeasureResultResponse(
            success=bool(result.get("success", False)),
            cup_available=bool(result.get("cup_available", False)),
            measured_height_z=float(result.get("measured_height_z") or 0.0),
            measured_diameter=float(result.get("measured_diameter") or 0.0),
            error_code=int(result.get("error_code") or 0),
            message=str(result.get("message") or ""),
            measured_at=datetime.now(timezone.utc),
        )
        self._latest_measure = response
        if websocket is not None:
            await websocket.send_json({"type": "result", **response.model_dump(mode="json")})
        return response


order_service = OrderService()
