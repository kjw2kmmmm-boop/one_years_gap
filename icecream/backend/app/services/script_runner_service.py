import asyncio
from collections.abc import Awaitable, Callable
import os
from pathlib import Path
import tempfile
import time

from ros_bridge.ros_env import get_ros_runtime_paths
from services.manual_control_service import manual_control_service
from services.order_service import order_service

LogCallback = Callable[[dict], Awaitable[None]]


class ScriptRunnerService:
    """대시보드에서 전달된 ROS2 Python 3.12 테스트 스크립트를 호스트에서 실행·제어한다."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._proc: asyncio.subprocess.Process | None = None
        self._stop_requested = False
        self._running = False
        self._running_client: str | None = None
        self._started_at: float | None = None
        self._status_subscribers: set[asyncio.Queue[dict]] = set()

    def is_running(self) -> bool:
        return self._proc is not None and self._proc.returncode is None

    def get_status(self) -> dict:
        running = self._running or self._lock.locked()
        return {
            "type": "script_status",
            "running": running,
            "client_ip": self._running_client if running else None,
            "started_at": self._started_at if running else None,
        }

    def subscribe_status(self) -> asyncio.Queue[dict]:
        queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=16)
        self._status_subscribers.add(queue)
        return queue

    def unsubscribe_status(self, queue: asyncio.Queue[dict]) -> None:
        self._status_subscribers.discard(queue)

    def _broadcast_status(self, payload: dict | None = None) -> None:
        msg = payload or self.get_status()
        for queue in list(self._status_subscribers):
            if queue.full():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            try:
                queue.put_nowait(msg)
            except asyncio.QueueFull:
                pass

    async def stop_current(self, *, stop_robot: bool = True) -> tuple[bool, str]:
        self._stop_requested = True
        killed = False

        if self._proc is not None and self._proc.returncode is None:
            killed = True
            self._proc.terminate()
            try:
                await asyncio.wait_for(self._proc.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                self._proc.kill()
                await self._proc.wait()

        if stop_robot:
            try:
                await manual_control_service.send_command({"cmd": "stop", "stop_mode": 1})
            except Exception:
                pass

        if killed:
            return True, "실행 중인 파이썬 스크립트를 중단하고 로봇 정지를 요청했습니다."
        return True, "실행 중인 스크립트는 없으나 로봇 정지 신호를 전송했습니다."

    async def run_script(
        self,
        *,
        code: str,
        timeout_sec: float = 120.0,
        auto_enter: bool = True,
        pin: str = "",
        client_ip: str | None = None,
        on_event: LogCallback,
    ) -> None:
        required_pin = os.getenv("SCRIPT_RUNNER_PIN", "").strip()
        if required_pin and pin.strip() != required_pin:
            await on_event(
                {
                    "type": "finished",
                    "success": False,
                    "returncode": -1,
                    "message": "실행 PIN이 올바르지 않습니다.",
                }
            )
            return

        if order_service.has_active_order():
            await on_event(
                {
                    "type": "finished",
                    "success": False,
                    "returncode": -1,
                    "message": "주문 제조가 진행 중일 때는 스크립트를 실행할 수 없습니다.",
                }
            )
            return

        if not code.strip():
            await on_event(
                {
                    "type": "finished",
                    "success": False,
                    "returncode": -1,
                    "message": "실행할 파이썬 코드가 비어 있습니다.",
                }
            )
            return

        if self._lock.locked():
            await on_event(
                {
                    "type": "finished",
                    "success": False,
                    "returncode": -1,
                    "message": "이미 다른 파이썬 스크립트가 실행 중입니다.",
                }
            )
            return

        ros_setup, ws_setup, ros_python = get_ros_runtime_paths()
        if not Path(ws_setup).is_file():
            await on_event(
                {
                    "type": "finished",
                    "success": False,
                    "returncode": -1,
                    "message": f"ROS2 워크스페이스 setup 스크립트를 찾을 수 없습니다: {ws_setup}",
                }
            )
            return

        timeout_sec = max(5.0, min(300.0, float(timeout_sec)))

        async with self._lock:
            self._stop_requested = False
            self._running = True
            self._running_client = client_ip or None
            self._started_at = time.time()
            self._broadcast_status()
            tmp_path: str | None = None

            try:
                with tempfile.NamedTemporaryFile(
                    mode="w",
                    suffix=".py",
                    prefix="icecream_remote_",
                    encoding="utf-8",
                    delete=False,
                ) as fp:
                    fp.write(code)
                    tmp_path = fp.name

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
                    "remote_python_runner",
                    ros_setup,
                    ws_setup,
                    ros_python,
                    tmp_path,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )

                if self._proc.stdin is not None:
                    if auto_enter:
                        self._proc.stdin.write(b"\n" * 20)
                        await self._proc.stdin.drain()
                    self._proc.stdin.close()

                await on_event(
                    {
                        "type": "started",
                        "message": f"스크립트 실행 시작 (timeout {timeout_sec:.0f}s)",
                    }
                )

                async def _pump_stream(stream: asyncio.StreamReader | None, stream_name: str) -> None:
                    if stream is None:
                        return
                    while True:
                        raw_line = await stream.readline()
                        if not raw_line:
                            break
                        text = raw_line.decode("utf-8", errors="replace").rstrip("\r\n")
                        await on_event(
                            {
                                "type": "log",
                                "stream": stream_name,
                                "line": text,
                            }
                        )

                pump_task = asyncio.gather(
                    _pump_stream(self._proc.stdout, "stdout"),
                    _pump_stream(self._proc.stderr, "stderr"),
                )

                timed_out = False
                try:
                    await asyncio.wait_for(pump_task, timeout=timeout_sec)
                    rc = await self._proc.wait()
                except asyncio.TimeoutError:
                    timed_out = True
                    await self.stop_current(stop_robot=True)
                    try:
                        await pump_task
                    except Exception:
                        pass
                    rc = -1

                if timed_out:
                    await on_event(
                        {
                            "type": "finished",
                            "success": False,
                            "returncode": rc,
                            "message": f"실행 시간 초과({timeout_sec:.0f}s)로 스크립트를 중단하고 로봇을 정지했습니다.",
                        }
                    )
                elif self._stop_requested:
                    await on_event(
                        {
                            "type": "finished",
                            "success": False,
                            "returncode": rc,
                            "message": "사용자에 의해 실행이 중단되었습니다.",
                        }
                    )
                elif rc == 0:
                    await on_event(
                        {
                            "type": "finished",
                            "success": True,
                            "returncode": rc,
                            "message": "스크립트 실행이 정상 완료되었습니다.",
                        }
                    )
                else:
                    await on_event(
                        {
                            "type": "finished",
                            "success": False,
                            "returncode": rc,
                            "message": f"스크립트가 오류로 종료되었습니다 (exit code {rc}).",
                        }
                    )
            except asyncio.CancelledError:
                await self.stop_current(stop_robot=True)
                raise
            finally:
                self._proc = None
                if tmp_path and os.path.exists(tmp_path):
                    try:
                        os.remove(tmp_path)
                    except OSError:
                        pass
                self._running = False
                self._running_client = None
                self._started_at = None
                # lock 해제 직전이라도 UI에는 실행 종료로 알리기 위해 명시적으로 running=False 전달
                self._broadcast_status(
                    {
                        "type": "script_status",
                        "running": False,
                        "client_ip": None,
                        "started_at": None,
                    }
                )


script_runner_service = ScriptRunnerService()
