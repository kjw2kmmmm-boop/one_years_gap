import asyncio
import json
from dataclasses import dataclass
from pathlib import Path

from ros_bridge.ros_env import get_ros_runtime_paths

_CALLER_SCRIPT = str(Path(__file__).resolve().with_name("ros_task_caller.py"))


class RosBridgeError(Exception):
    """ROS2 브리지 호출 중 발생한 일반 오류."""


class RosServiceUnavailableError(RosBridgeError):
    """ROS2 서비스가 실행 중이지 않거나 연결할 수 없는 경우."""


class RosServiceTimeoutError(RosBridgeError):
    """ROS2 서비스 응답이 제한 시간 내에 도착하지 않은 경우."""


@dataclass(frozen=True)
class ExecuteTaskResult:
    success: bool
    error_code: int
    message: str


def _parse_last_json_line(stdout_text: str) -> dict | None:
    for line in reversed(stdout_text.splitlines()):
        stripped = line.strip()
        if stripped.startswith("{") and stripped.endswith("}"):
            try:
                return json.loads(stripped)
            except json.JSONDecodeError:
                continue
    return None


async def execute_task(
    command: str,
    target: str = "",
    *,
    service_name: str = "/execute_task",
    wait_timeout: float = 3.0,
    call_timeout: float = 30.0,
) -> ExecuteTaskResult:
    """ROS2 ExecuteTask 서비스(/execute_task)를 비동기로 호출한다."""
    ros_setup, ws_setup, ros_python = get_ros_runtime_paths()

    if not Path(ws_setup).is_file():
        raise RosServiceUnavailableError(
            f"ROS2 workspace setup script not found: {ws_setup} (colcon build 필요)"
        )

    bash_script = (
        'set -e; '
        'if [ -f "$1" ]; then source "$1"; fi; '
        'source "$2"; '
        'exec "$3" "$4" '
        '--service "$5" '
        '--command "$6" '
        '--target "$7" '
        '--wait-timeout "$8" '
        '--call-timeout "$9"'
    )

    proc = await asyncio.create_subprocess_exec(
        "/bin/bash",
        "-c",
        bash_script,
        "ros_task_caller",
        ros_setup,
        ws_setup,
        ros_python,
        _CALLER_SCRIPT,
        service_name,
        command,
        target,
        str(wait_timeout),
        str(call_timeout),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    total_timeout = wait_timeout + call_timeout + 5.0
    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(),
            timeout=total_timeout,
        )
    except asyncio.TimeoutError as exc:
        proc.kill()
        await proc.wait()
        raise RosServiceTimeoutError(
            f"ROS2 ExecuteTask('{command}') timed out after {total_timeout:.1f}s"
        ) from exc

    stdout_text = stdout_bytes.decode("utf-8", errors="replace")
    stderr_text = stderr_bytes.decode("utf-8", errors="replace").strip()
    payload = _parse_last_json_line(stdout_text)

    if proc.returncode == 0 and payload is not None:
        return ExecuteTaskResult(
            success=bool(payload.get("success", False)),
            error_code=int(payload.get("error_code", 1)),
            message=str(payload.get("message", "")),
        )

    detail = (payload or {}).get("message") or stderr_text or stdout_text.strip()
    if proc.returncode == 2:
        raise RosServiceUnavailableError(detail or f"ROS2 service '{service_name}' unavailable")
    if proc.returncode == 3:
        raise RosServiceTimeoutError(detail or f"ROS2 service '{service_name}' timed out")
    raise RosBridgeError(detail or f"ROS2 bridge exited with code {proc.returncode}")
