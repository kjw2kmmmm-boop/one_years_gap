import asyncio
from collections.abc import Awaitable, Callable
import json
from pathlib import Path

from ros_bridge.execute_task_client import (
    RosBridgeError,
    RosServiceTimeoutError,
    RosServiceUnavailableError,
)
from ros_bridge.ros_env import get_ros_runtime_paths

_ACTION_CALLER_SCRIPT = str(Path(__file__).resolve().with_name("ros_action_caller.py"))

ActionEventCallback = Callable[[dict], Awaitable[None]]


async def run_ros_action(
    *,
    action_type: str,
    action_name: str,
    goal_payload: dict,
    on_event: ActionEventCallback | None = None,
    wait_timeout: float = 3.0,
    call_timeout: float = 300.0,
) -> dict:
    """ROS2 Action 워커 서브프로세스를 실행하고 피드백/결과 JSON 이벤트를 스트리밍한다."""
    ros_setup, ws_setup, ros_python = get_ros_runtime_paths()

    if not Path(ws_setup).is_file():
        raise RosServiceUnavailableError(
            f"ROS2 workspace setup script not found: {ws_setup} (colcon build 필요)"
        )

    bash_script = (
        'set -e; '
        'if [ -f "$1" ]; then source "$1"; fi; '
        'source "$2"; '
        'exec "$3" -u "$4" '
        '--action-type "$5" '
        '--action-name "$6" '
        '--goal "$7" '
        '--wait-timeout "$8" '
        '--call-timeout "$9"'
    )

    proc = await asyncio.create_subprocess_exec(
        "/bin/bash",
        "-c",
        bash_script,
        "ros_action_caller",
        ros_setup,
        ws_setup,
        ros_python,
        _ACTION_CALLER_SCRIPT,
        action_type,
        action_name,
        json.dumps(goal_payload, ensure_ascii=False),
        str(wait_timeout),
        str(call_timeout),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    final_result: dict | None = None
    assert proc.stdout is not None
    assert proc.stderr is not None

    try:
        while True:
            line = await asyncio.wait_for(
                proc.stdout.readline(),
                timeout=wait_timeout + call_timeout + 10.0,
            )
            if not line:
                break
            text = line.decode("utf-8", errors="replace").strip()
            if not text.startswith("{"):
                continue
            try:
                event = json.loads(text)
            except json.JSONDecodeError:
                continue

            if event.get("type") == "result":
                final_result = event
            if on_event is not None:
                await on_event(event)

        await proc.wait()
    except asyncio.TimeoutError as exc:
        proc.kill()
        await proc.wait()
        raise RosServiceTimeoutError(
            f"ROS2 Action '{action_name}' timed out"
        ) from exc
    except asyncio.CancelledError:
        if proc.returncode is None:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
        raise

    stderr_text = (await proc.stderr.read()).decode("utf-8", errors="replace").strip()

    if final_result is None:
        detail = stderr_text or f"ROS2 Action '{action_name}' exited with code {proc.returncode}"
        raise RosBridgeError(detail)

    if proc.returncode == 2:
        raise RosServiceUnavailableError(final_result.get("message", "Action server unavailable"))
    if proc.returncode == 3:
        raise RosServiceTimeoutError(final_result.get("message", "Action execution timed out"))

    return final_result
