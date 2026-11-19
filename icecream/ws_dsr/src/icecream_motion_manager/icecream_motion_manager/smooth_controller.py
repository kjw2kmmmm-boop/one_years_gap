import os
import statistics
import time

from dsr_msgs2.srv import (
    CheckMotion,
    GetCurrentPosx,
    GetToolForce,
    MoveLine,
    MoveStop,
)
import rclpy

from icecream_motion_manager.pose_config import get_section_config

ROBOT_ID = "dsr01"
ROBOT_MODEL = "m0609"

SYSTEM_HOME = [0.0, 0.0, 90.0, 0.0, 90.0, 0.0]

DEFAULT_WORKSPACE_CONSTANTS = {
    "vel_j": 50.0,
    "acc_j": 80.0,
    "vel_x": 100.0,
    "acc_x": 200.0,
    "safe_z": 410.0,
    "corner_x": 273.0,
    "corner_y": -225.0,
    "grid_step_mm": 150.0,
    "abort_force": 8.0,
    "hits_required": 2.0,
    "sample_sleep": 0.025,
}


def grid_to_xy(
    gx: float,
    gy: float,
    *,
    corner_x: float = 273.0,
    corner_y: float = -225.0,
    step_mm: float = 150.0,
) -> tuple[float, float]:
    """그리드 좌표를 로봇 BASE XY 좌표(mm)로 변환한다."""
    return corner_x + (gx * step_mm), corner_y + (gy * step_mm)


def load_section_params(section: str, defaults: dict[str, float]) -> dict[str, float]:
    """poses.yaml 섹션 설정을 읽어 기본값과 병합한다."""
    try:
        cfg = get_section_config(section)
    except Exception:
        cfg = {}
    return {key: float(cfg.get(key, default)) for key, default in defaults.items()}


class SmoothController:
    """MoveLine(sync_type=1) + 힘/위치 폴링 기반 스무스 접촉 정지 컨트롤러."""

    def __init__(
        self,
        node,
        *,
        robot_id: str | None = None,
        sample_sleep: float = 0.025,
    ) -> None:
        self.node = node
        self.sample_sleep = sample_sleep
        rid = (robot_id or os.getenv("ROBOT_ID", ROBOT_ID)).strip("/")
        prefix = f"/{rid}/dsr_controller2"

        service_specs = (
            ("move", MoveLine, f"{prefix}/motion/move_line"),
            ("stop", MoveStop, f"{prefix}/motion/move_stop"),
            ("check", CheckMotion, f"{prefix}/motion/check_motion"),
            ("pose", GetCurrentPosx, f"{prefix}/aux_control/get_current_posx"),
            ("force", GetToolForce, f"{prefix}/aux_control/get_tool_force"),
        )
        self.clients = {}
        try:
            for name, srv_type, srv_name in service_specs:
                client = node.create_client(srv_type, srv_name)
                self.clients[name] = client
                if not client.wait_for_service(timeout_sec=3.0):
                    raise RuntimeError(f"ROS2 서비스 연결 실패: {srv_name}")
        except Exception:
            self.close()
            raise

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def close(self) -> None:
        """생성한 ROS2 서비스 클라이언트를 모두 정리한다."""
        for client in self.clients.values():
            try:
                self.node.destroy_client(client)
            except Exception:
                pass
        self.clients.clear()

    def call(self, name: str, req, timeout: float = 2.5):
        future = self.clients[name].call_async(req)
        rclpy.spin_until_future_complete(self.node, future, timeout_sec=timeout)
        if not future.done():
            future.cancel()
            raise TimeoutError(f"{name} 응답 시간 초과")
        return future.result()

    def pose(self) -> list[float]:
        req = GetCurrentPosx.Request()
        req.ref = 0
        data = self.call("pose", req).task_pos_info
        if not data:
            raise RuntimeError("현재 TCP 좌표 확인 실패")
        return [float(v) for v in data[0].data[:6]]

    def force(self) -> tuple[float, float, float]:
        req = GetToolForce.Request()
        req.ref = 0
        f = self.call("force", req).tool_force
        return float(f[0]), float(f[1]), float(f[2])

    def status(self) -> int:
        return int(self.call("check", CheckMotion.Request()).status)

    def start_move(self, target: list[float], speed: float, acc: float) -> None:
        req = MoveLine.Request()
        req.pos = [float(v) for v in target]
        req.vel = [float(speed), 0.0]
        req.acc = [float(acc), 0.0]
        req.time = 0.0
        req.radius = 0.0
        req.ref = 0
        req.mode = 0
        req.blend_type = 0
        req.sync_type = 1
        self.call("move", req, timeout=5.0)

    def stop(self) -> list[float]:
        req = MoveStop.Request()
        req.stop_mode = 1
        self.call("stop", req, timeout=3.0)
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            if self.status() == 0:
                return self.pose()
            time.sleep(0.03)
        return self.pose()

    def read_baseline(self, count: int = 7) -> tuple[float, float, float]:
        samples = []
        for _ in range(count):
            samples.append(self.force())
            time.sleep(self.sample_sleep)
        return tuple(statistics.median(s[i] for s in samples) for i in range(3))

    def monitor_motion(self, target: list[float], timeout: float = 60.0):
        import math

        started = time.monotonic()
        was_busy = False
        while time.monotonic() - started < timeout:
            here = self.pose()
            f = self.force()
            yield here, f

            st = self.status()
            if st != 0:
                was_busy = True
            elif math.dist(here[:3], target[:3]) <= 1.5:
                return
            elif was_busy and time.monotonic() - started > 0.5:
                return
            time.sleep(self.sample_sleep)
