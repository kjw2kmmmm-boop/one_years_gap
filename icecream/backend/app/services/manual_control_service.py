import asyncio
import json
from pathlib import Path

from fastapi import status

from ros_bridge.ros_env import get_ros_runtime_paths
from schemas.manual import ManualControlResponse

_WORKER_SCRIPT = str(Path(__file__).resolve().parents[1] / "ros_bridge" / "ros_manual_worker.py")


class ManualControlError(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


class ManualControlService:
    """상주형 ROS2 수동 제어 워커와 통신하며 스텝·조그·정지·속도·모드 명령을 전달한다."""

    def __init__(self) -> None:
        self._proc: asyncio.subprocess.Process | None = None
        self._reader_task: asyncio.Task | None = None
        self._pending: dict[int, asyncio.Future] = {}
        self._next_req_id = 1
        self._start_lock = asyncio.Lock()
        self._write_lock = asyncio.Lock()
        self._running = False

    async def start(self) -> None:
        self._running = True
        await self._ensure_worker()

    async def stop(self) -> None:
        self._running = False
        for fut in list(self._pending.values()):
            if not fut.done():
                fut.set_result({"success": False, "message": "서버 종료 중"})
        self._pending.clear()

        if self._proc is not None and self._proc.returncode is None:
            if self._proc.stdin is not None:
                try:
                    self._proc.stdin.close()
                except Exception:
                    pass
            try:
                await asyncio.wait_for(self._proc.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                self._proc.kill()
                await self._proc.wait()
        self._proc = None

        if self._reader_task is not None:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
            self._reader_task = None

    async def _ensure_worker(self) -> None:
        async with self._start_lock:
            if self._proc is not None and self._proc.returncode is None:
                return
            ros_setup, ws_setup, ros_python = get_ros_runtime_paths()
            if not Path(ws_setup).is_file():
                raise ManualControlError(
                    status.HTTP_503_SERVICE_UNAVAILABLE,
                    f"ROS2 workspace setup script not found: {ws_setup}",
                )

            bash_script = (
                'set -e; '
                'if [ -f "$1" ]; then source "$1"; fi; '
                'source "$2"; '
                'exec "$3" -u "$4"'
            )
            self._proc = await asyncio.create_subprocess_exec(
                "/bin/bash",
                "-c",
                bash_script,
                "ros_manual_worker",
                ros_setup,
                ws_setup,
                ros_python,
                _WORKER_SCRIPT,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            self._reader_task = asyncio.create_task(self._read_loop())

    async def _read_loop(self) -> None:
        assert self._proc is not None and self._proc.stdout is not None
        try:
            while self._running:
                line = await self._proc.stdout.readline()
                if not line:
                    break
                text = line.decode("utf-8", errors="replace").strip()
                if not text.startswith("{"):
                    continue
                try:
                    data = json.loads(text)
                except json.JSONDecodeError:
                    continue
                req_id = data.get("req_id")
                fut = self._pending.pop(req_id, None)
                if fut is not None and not fut.done():
                    fut.set_result(data)
        except asyncio.CancelledError:
            raise
        finally:
            for fut in list(self._pending.values()):
                if not fut.done():
                    fut.set_result({"success": False, "message": "수동 제어 워커 연결이 종료되었습니다."})
            self._pending.clear()

    async def send_command(self, payload: dict, *, timeout: float = 3.0) -> ManualControlResponse:
        await self._ensure_worker()
        assert self._proc is not None and self._proc.stdin is not None

        loop = asyncio.get_running_loop()
        req_id = self._next_req_id
        self._next_req_id += 1
        fut: asyncio.Future = loop.create_future()
        self._pending[req_id] = fut

        wire_payload = json.dumps({"req_id": req_id, **payload}, ensure_ascii=False) + "\n"
        try:
            async with self._write_lock:
                self._proc.stdin.write(wire_payload.encode("utf-8"))
                await self._proc.stdin.drain()
            result = await asyncio.wait_for(fut, timeout=timeout)
        except asyncio.TimeoutError as exc:
            self._pending.pop(req_id, None)
            raise ManualControlError(
                status.HTTP_504_GATEWAY_TIMEOUT,
                "수동 제어 명령 응답 시간 초과",
            ) from exc
        except Exception as exc:
            self._pending.pop(req_id, None)
            raise ManualControlError(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                f"수동 제어 워커 통신 오류: {exc}",
            ) from exc

        return ManualControlResponse(
            success=bool(result.get("success", False)),
            message=str(result.get("message", "")),
        )


manual_control_service = ManualControlService()
