import asyncio
import json

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, status

from schemas.manual import (
    ManualControlResponse,
    ManualModeRequest,
    ManualSpeedRequest,
    ManualStepRequest,
    ManualStopRequest,
)
from services.manual_control_service import ManualControlError, manual_control_service
from services.order_service import order_service
from services.script_runner_service import script_runner_service

manual = APIRouter(prefix="/manual", tags=["manual"])


def _ensure_not_running_order() -> None:
    if order_service.has_active_order():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="주문 제조가 진행 중일 때는 수동 이동을 실행할 수 없습니다.",
        )


async def _dispatch(payload: dict) -> ManualControlResponse:
    try:
        res = await manual_control_service.send_command(payload)
    except ManualControlError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    if not res.success:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=res.message)
    return res


@manual.post(
    "/step",
    response_model=ManualControlResponse,
    status_code=status.HTTP_200_OK,
    description="Task/Joint 스텝(증분) 이동",
)
async def manual_step(payload: ManualStepRequest) -> ManualControlResponse:
    _ensure_not_running_order()
    return await _dispatch({"cmd": "step_move", **payload.model_dump()})


@manual.post(
    "/stop",
    response_model=ManualControlResponse,
    status_code=status.HTTP_200_OK,
    description="로봇 즉시 정지 (주문 실행 중에도 항상 허용)",
)
async def manual_stop(payload: ManualStopRequest | None = None) -> ManualControlResponse:
    req = payload or ManualStopRequest()
    return await _dispatch({"cmd": "stop", "stop_mode": req.stop_mode})


@manual.post(
    "/speed",
    response_model=ManualControlResponse,
    status_code=status.HTTP_200_OK,
    description="로봇 전체 속도 배율(%) 변경",
)
async def manual_speed(payload: ManualSpeedRequest) -> ManualControlResponse:
    return await _dispatch({"cmd": "set_speed", "speed": payload.speed})


@manual.post(
    "/mode",
    response_model=ManualControlResponse,
    status_code=status.HTTP_200_OK,
    description="로봇 모드 전환 (MANUAL / AUTONOMOUS)",
)
async def manual_mode(payload: ManualModeRequest) -> ManualControlResponse:
    _ensure_not_running_order()
    return await _dispatch({"cmd": "set_mode", "robot_mode": payload.robot_mode})


@manual.websocket("/ws/jog")
async def manual_jog_ws(websocket: WebSocket) -> None:
    """Hold-to-Jog 연속 조그 및 하트비트 감시용 WebSocket."""
    await websocket.accept()
    jogging = False
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"success": False, "message": "잘못된 JSON 형식"})
                continue

            msg_type = str(msg.get("type", ""))
            if msg_type == "jog_start":
                if order_service.has_active_order():
                    await websocket.send_json(
                        {"success": False, "message": "주문 제조 진행 중에는 조그할 수 없습니다."}
                    )
                    continue
                res = await manual_control_service.send_command(
                    {
                        "cmd": "jog_start",
                        "jog_axis": int(msg.get("jog_axis", 0)),
                        "move_reference": int(msg.get("move_reference", 0)),
                        "speed": float(msg.get("speed", 20.0)),
                    }
                )
                jogging = res.success
                await websocket.send_json(res.model_dump())
            elif msg_type == "heartbeat":
                if jogging:
                    await manual_control_service.send_command({"cmd": "jog_heartbeat"})
            elif msg_type == "jog_stop":
                jogging = False
                res = await manual_control_service.send_command({"cmd": "jog_stop"})
                await websocket.send_json(res.model_dump())
            else:
                await websocket.send_json({"success": False, "message": f"알 수 없는 명령: {msg_type}"})
    except WebSocketDisconnect:
        pass
    finally:
        if jogging:
            try:
                await manual_control_service.send_command({"cmd": "jog_stop"})
            except Exception:
                pass


@manual.get(
    "/script/status",
    status_code=status.HTTP_200_OK,
    description="원격 파이썬 스크립트 실행 중 여부 조회",
)
async def get_remote_script_status() -> dict:
    return script_runner_service.get_status()


@manual.websocket("/ws/script-status")
async def remote_script_status_ws(websocket: WebSocket) -> None:
    """원격 파이썬 스크립트 실행 상태를 접속한 모든 대시보드에 실시간으로 전달한다."""
    await websocket.accept()
    queue = script_runner_service.subscribe_status()

    async def _drain_rx() -> None:
        try:
            while True:
                await websocket.receive_text()
        except Exception:
            return

    rx_task = asyncio.create_task(_drain_rx())
    try:
        await websocket.send_json(script_runner_service.get_status())
        while not rx_task.done():
            get_task = asyncio.create_task(queue.get())
            done, _ = await asyncio.wait(
                {rx_task, get_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if get_task in done:
                await websocket.send_json(get_task.result())
            else:
                get_task.cancel()
                break
    except WebSocketDisconnect:
        pass
    finally:
        rx_task.cancel()
        try:
            await rx_task
        except asyncio.CancelledError:
            pass
        script_runner_service.unsubscribe_status(queue)


@manual.post(
    "/script/stop",
    response_model=ManualControlResponse,
    status_code=status.HTTP_200_OK,
    description="실행 중인 원격 파이썬 스크립트 중단 및 로봇 정지",
)
async def stop_remote_script() -> ManualControlResponse:
    ok, msg = await script_runner_service.stop_current(stop_robot=True)
    return ManualControlResponse(success=ok, message=msg)


@manual.websocket("/ws/script")
async def run_remote_script_ws(websocket: WebSocket) -> None:
    """대시보드에서 전송한 파이썬 코드를 호스트 ROS2 환경에서 실행하고 로그를 스트리밍한다."""
    await websocket.accept()
    run_task: asyncio.Task | None = None

    async def _send_event(event: dict) -> None:
        try:
            await websocket.send_json(event)
        except Exception:
            pass

    try:
        raw = await websocket.receive_text()
        payload = json.loads(raw)
        code = str(payload.get("code", ""))
        timeout_sec = float(payload.get("timeout_sec", 120.0))
        auto_enter = bool(payload.get("auto_enter", True))
        pin = str(payload.get("pin", ""))

        forwarded_for = websocket.headers.get("x-forwarded-for", "").split(",")[0].strip()
        client_ip = forwarded_for or (websocket.client.host if websocket.client else None)

        run_task = asyncio.create_task(
            script_runner_service.run_script(
                code=code,
                timeout_sec=timeout_sec,
                auto_enter=auto_enter,
                pin=pin,
                client_ip=client_ip,
                on_event=_send_event,
            )
        )

        async def _watch_client() -> None:
            while not run_task.done():
                msg_text = await websocket.receive_text()
                try:
                    msg = json.loads(msg_text)
                    if msg.get("type") == "stop":
                        await script_runner_service.stop_current(stop_robot=True)
                except Exception:
                    pass

        watch_task = asyncio.create_task(_watch_client())
        try:
            await run_task
        finally:
            watch_task.cancel()
            try:
                await watch_task
            except (asyncio.CancelledError, WebSocketDisconnect):
                pass

        await websocket.close()
    except WebSocketDisconnect:
        if run_task is not None and not run_task.done():
            await script_runner_service.stop_current(stop_robot=True)
            run_task.cancel()
            try:
                await run_task
            except asyncio.CancelledError:
                pass
    except Exception as exc:
        await _send_event(
            {
                "type": "finished",
                "success": False,
                "returncode": -1,
                "message": f"스크립트 실행 요청 오류: {exc}",
            }
        )
        try:
            await websocket.close()
        except Exception:
            pass
