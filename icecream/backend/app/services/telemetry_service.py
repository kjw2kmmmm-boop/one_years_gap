import asyncio
import json
import os
import time
from pathlib import Path

from fastapi import WebSocket

from ros_bridge.ros_env import get_ros_runtime_paths
from schemas.dashboard import TelemetrySnapshot

_SUBSCRIBER_SCRIPT = str(
    Path(__file__).resolve().parents[1] / "ros_bridge" / "ros_telemetry_subscriber.py"
)


class TelemetryService:
    """ROS2 /dashboard/telemetry 토픽을 구독해 최신 상태와 WebSocket 브로드캐스트를 관리한다."""

    def __init__(self, topic_name: str = "/dashboard/telemetry") -> None:
        self._topic_name = os.getenv("TELEMETRY_TOPIC", topic_name)
        self._stale_after_sec = 3.0
        self._latest = TelemetrySnapshot(connected=False)
        self._last_received_monotonic = 0.0
        self._clients: set[WebSocket] = set()
        self._runner_task: asyncio.Task | None = None
        self._proc: asyncio.subprocess.Process | None = None
        self._running = False

    def get_snapshot(self) -> TelemetrySnapshot:
        is_fresh = (
            self._last_received_monotonic > 0.0
            and (time.monotonic() - self._last_received_monotonic) <= self._stale_after_sec
        )
        return self._latest.model_copy(update={"connected": is_fresh})

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._runner_task = asyncio.create_task(self._stream_loop())

    async def stop(self) -> None:
        self._running = False
        if self._proc is not None and self._proc.returncode is None:
            self._proc.terminate()
            try:
                await asyncio.wait_for(self._proc.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                self._proc.kill()
                await self._proc.wait()
        if self._runner_task is not None:
            self._runner_task.cancel()
            try:
                await self._runner_task
            except asyncio.CancelledError:
                pass
            self._runner_task = None

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._clients.add(websocket)
        await websocket.send_json(self.get_snapshot().model_dump())

    def disconnect(self, websocket: WebSocket) -> None:
        self._clients.discard(websocket)

    async def _broadcast(self, snapshot: TelemetrySnapshot) -> None:
        if not self._clients:
            return
        payload = snapshot.model_dump()
        disconnected: list[WebSocket] = []
        for ws in list(self._clients):
            try:
                await ws.send_json(payload)
            except Exception:
                disconnected.append(ws)
        for ws in disconnected:
            self._clients.discard(ws)

    async def _stream_loop(self) -> None:
        while self._running:
            ros_setup, ws_setup, ros_python = get_ros_runtime_paths()
            if not Path(ws_setup).is_file():
                await asyncio.sleep(2.0)
                continue

            bash_script = (
                'set -e; '
                'if [ -f "$1" ]; then source "$1"; fi; '
                'source "$2"; '
                'exec "$3" -u "$4" --topic "$5"'
            )

            try:
                self._proc = await asyncio.create_subprocess_exec(
                    "/bin/bash",
                    "-c",
                    bash_script,
                    "ros_telemetry_subscriber",
                    ros_setup,
                    ws_setup,
                    ros_python,
                    _SUBSCRIBER_SCRIPT,
                    self._topic_name,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )

                assert self._proc.stdout is not None
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

                    self._last_received_monotonic = time.monotonic()
                    self._latest = TelemetrySnapshot(connected=True, **data)
                    await self._broadcast(self._latest)

                await self._proc.wait()
            except asyncio.CancelledError:
                raise
            except Exception:
                pass
            finally:
                self._proc = None

            if self._running:
                await asyncio.sleep(1.5)


telemetry_service = TelemetryService()
