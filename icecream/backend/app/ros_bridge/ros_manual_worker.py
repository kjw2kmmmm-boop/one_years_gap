"""ROS2 Python 3.12 환경에서 상주하며 조그/스텝/정지/속도/모드 서비스를 저지연 처리하는 워커.

연속 조그(Hold-to-Jog) 중 stdin 종료 또는 하트비트 타임아웃(0.35s)이 발생하면
워치독 타이머가 즉시 Jog(speed=0) + MoveStop을 호출해 로봇 폭주를 방지한다.
"""

import json
import os
import sys
import threading
import time

import rclpy
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node

from dsr_msgs2.srv import (
    ChangeOperationSpeed,
    GetCurrentPosx,
    Jog,
    MoveJoint,
    MoveLine,
    MoveStop,
    SetRobotMode,
)

MAX_MANUAL_SPEED_PCT = float(os.getenv("MANUAL_MAX_SPEED_PCT", "50.0"))
MIN_SAFE_Z_MM = float(os.getenv("MANUAL_MIN_SAFE_Z_MM", "50.0"))
JOG_WATCHDOG_TIMEOUT_SEC = 0.35


class ManualControlWorker(Node):
    def __init__(self, robot_id: str) -> None:
        super().__init__("backend_manual_control_worker")
        self._cb_group = ReentrantCallbackGroup()
        prefix = f"/{robot_id.strip('/')}/dsr_controller2"

        self._jog_cli = self.create_client(Jog, f"{prefix}/motion/jog", callback_group=self._cb_group)
        self._stop_cli = self.create_client(MoveStop, f"{prefix}/motion/move_stop", callback_group=self._cb_group)
        self._movel_cli = self.create_client(MoveLine, f"{prefix}/motion/move_line", callback_group=self._cb_group)
        self._movej_cli = self.create_client(MoveJoint, f"{prefix}/motion/move_joint", callback_group=self._cb_group)
        self._speed_cli = self.create_client(
            ChangeOperationSpeed, f"{prefix}/motion/change_operation_speed", callback_group=self._cb_group
        )
        self._mode_cli = self.create_client(
            SetRobotMode, f"{prefix}/system/set_robot_mode", callback_group=self._cb_group
        )
        self._posx_cli = self.create_client(
            GetCurrentPosx, f"{prefix}/aux_control/get_current_posx", callback_group=self._cb_group
        )

        self._jog_lock = threading.Lock()
        self._jog_active = False
        self._jog_axis = 0
        self._jog_ref = 0
        self._last_jog_heartbeat = 0.0

        self._watchdog_timer = self.create_timer(
            0.05, self._check_jog_watchdog, callback_group=self._cb_group
        )

    def _call_sync(self, client, req, timeout_sec: float = 2.0):
        if not client.wait_for_service(timeout_sec=1.0):
            raise RuntimeError(f"ROS2 서비스({client.srv_name})가 준비되지 않았습니다.")
        done = threading.Event()
        future = client.call_async(req)
        future.add_done_callback(lambda _f: done.set())
        if not done.wait(timeout=timeout_sec):
            raise RuntimeError(f"ROS2 서비스({client.srv_name}) 응답 시간 초과")
        exc = future.exception()
        if exc is not None:
            raise RuntimeError(str(exc))
        return future.result()

    def _force_stop_jog(self, axis: int, ref: int, *, stop_mode: int = 2) -> None:
        try:
            jog_req = Jog.Request()
            jog_req.jog_axis = int(axis)
            jog_req.move_reference = int(ref)
            jog_req.speed = 0.0
            if self._jog_cli.service_is_ready():
                self._call_sync(self._jog_cli, jog_req, timeout_sec=1.0)
        except Exception:
            pass
        try:
            stop_req = MoveStop.Request()
            stop_req.stop_mode = int(stop_mode)
            if self._stop_cli.service_is_ready():
                self._call_sync(self._stop_cli, stop_req, timeout_sec=1.0)
        except Exception:
            pass

    def _check_jog_watchdog(self) -> None:
        with self._jog_lock:
            if not self._jog_active:
                return
            if (time.monotonic() - self._last_jog_heartbeat) <= JOG_WATCHDOG_TIMEOUT_SEC:
                return
            axis = self._jog_axis
            ref = self._jog_ref
            self._jog_active = False
        self._force_stop_jog(axis, ref, stop_mode=2)

    def handle_command(self, payload: dict) -> dict:
        cmd = str(payload.get("cmd", "")).strip()
        try:
            if cmd == "jog_start":
                return self._handle_jog_start(payload)
            if cmd == "jog_heartbeat":
                return self._handle_jog_heartbeat()
            if cmd == "jog_stop":
                return self._handle_jog_stop()
            if cmd == "step_move":
                return self._handle_step_move(payload)
            if cmd == "stop":
                return self._handle_stop(payload)
            if cmd == "set_speed":
                return self._handle_set_speed(payload)
            if cmd == "set_mode":
                return self._handle_set_mode(payload)
            return {"success": False, "message": f"알 수 없는 수동 제어 명령: {cmd}"}
        except Exception as exc:
            return {"success": False, "message": str(exc)}

    def _handle_jog_start(self, payload: dict) -> dict:
        axis = int(payload["jog_axis"])
        ref = int(payload.get("move_reference", 0))
        raw_speed = float(payload.get("speed", 20.0))
        clamped_mag = max(1.0, min(MAX_MANUAL_SPEED_PCT, abs(raw_speed)))
        speed = clamped_mag if raw_speed >= 0 else -clamped_mag

        req = Jog.Request()
        req.jog_axis = axis
        req.move_reference = ref
        req.speed = speed
        resp = self._call_sync(self._jog_cli, req, timeout_sec=1.5)
        if not resp.success:
            return {"success": False, "message": "Jog 시작 명령이 거부되었습니다."}

        with self._jog_lock:
            self._jog_active = True
            self._jog_axis = axis
            self._jog_ref = ref
            self._last_jog_heartbeat = time.monotonic()
        return {"success": True, "message": f"Jog 시작 (axis={axis}, speed={speed:.0f}%)"}

    def _handle_jog_heartbeat(self) -> dict:
        with self._jog_lock:
            if self._jog_active:
                self._last_jog_heartbeat = time.monotonic()
                return {"success": True, "message": "heartbeat ok"}
        return {"success": False, "message": "jog not active"}

    def _handle_jog_stop(self) -> dict:
        with self._jog_lock:
            axis = self._jog_axis
            ref = self._jog_ref
            self._jog_active = False
        self._force_stop_jog(axis, ref, stop_mode=2)
        return {"success": True, "message": "Jog 정지 완료"}

    def _handle_stop(self, payload: dict) -> dict:
        stop_mode = int(payload.get("stop_mode", 1))
        with self._jog_lock:
            axis = self._jog_axis
            ref = self._jog_ref
            was_jogging = self._jog_active
            self._jog_active = False
        if was_jogging:
            self._force_stop_jog(axis, ref, stop_mode=stop_mode)
            return {"success": True, "message": "로봇 정지 명령 전송 완료"}

        req = MoveStop.Request()
        req.stop_mode = stop_mode
        resp = self._call_sync(self._stop_cli, req, timeout_sec=1.5)
        return {
            "success": bool(resp.success),
            "message": "로봇 정지 완료" if resp.success else "로봇 정지 요청 실패",
        }

    def _handle_step_move(self, payload: dict) -> dict:
        space = str(payload.get("space", "task")).lower()
        axis = int(payload["axis"])
        delta = float(payload["delta"])
        ref = int(payload.get("move_reference", 0))
        speed_pct = max(5.0, min(MAX_MANUAL_SPEED_PCT, float(payload.get("speed_pct", 25.0))))

        if space == "task":
            if ref == 0 and axis == 2 and delta < 0:
                posx_req = GetCurrentPosx.Request()
                posx_req.ref = 0
                posx_resp = self._call_sync(self._posx_cli, posx_req, timeout_sec=1.5)
                if posx_resp.success and posx_resp.task_pos_info:
                    curr_z = float(posx_resp.task_pos_info[0].data[2])
                    if curr_z + delta < MIN_SAFE_Z_MM:
                        return {
                            "success": False,
                            "message": f"안전 Z 하한({MIN_SAFE_Z_MM:.0f}mm) 미만으로 하강할 수 없습니다 (현재 {curr_z:.1f}mm).",
                        }

            pos = [0.0] * 6
            pos[axis] = delta
            lin_vel = max(10.0, min(120.0, speed_pct * 2.0))
            ang_vel = max(10.0, min(45.0, speed_pct * 0.8))

            req = MoveLine.Request()
            req.pos = pos
            req.vel = [lin_vel, ang_vel]
            req.acc = [80.0, 40.0]
            req.time = 0.0
            req.radius = 0.0
            req.ref = ref
            req.mode = 1  # DR_MV_MOD_REL
            req.blend_type = 0
            req.sync_type = 1  # ASYNC
            resp = self._call_sync(self._movel_cli, req, timeout_sec=2.0)
            return {
                "success": bool(resp.success),
                "message": "Task 스텝 이동 완료" if resp.success else "Task 스텝 이동 실패",
            }

        if space == "joint":
            pos = [0.0] * 6
            pos[axis] = delta
            j_vel = max(5.0, min(60.0, speed_pct))

            req = MoveJoint.Request()
            req.pos = pos
            req.vel = j_vel
            req.acc = j_vel
            req.time = 0.0
            req.radius = 0.0
            req.mode = 1  # MOVE_MODE_RELATIVE
            req.blend_type = 0
            req.sync_type = 1  # ASYNC
            resp = self._call_sync(self._movej_cli, req, timeout_sec=2.0)
            return {
                "success": bool(resp.success),
                "message": "Joint 스텝 이동 완료" if resp.success else "Joint 스텝 이동 실패",
            }

        return {"success": False, "message": f"지원하지 않는 좌표 공간: {space}"}

    def _handle_set_speed(self, payload: dict) -> dict:
        speed = max(1, min(100, int(payload["speed"])))
        req = ChangeOperationSpeed.Request()
        req.speed = speed
        resp = self._call_sync(self._speed_cli, req, timeout_sec=1.5)
        return {
            "success": bool(resp.success),
            "message": f"속도 배율 {speed}% 설정 완료" if resp.success else "속도 배율 설정 실패",
        }

    def _handle_set_mode(self, payload: dict) -> dict:
        mode = int(payload["robot_mode"])
        req = SetRobotMode.Request()
        req.robot_mode = mode
        resp = self._call_sync(self._mode_cli, req, timeout_sec=1.5)
        label = {0: "MANUAL", 1: "AUTONOMOUS", 2: "MEASURE"}.get(mode, str(mode))
        return {
            "success": bool(resp.success),
            "message": f"로봇 모드 {label} 전환 완료" if resp.success else "로봇 모드 전환 실패",
        }

    def stop_on_shutdown(self) -> None:
        with self._jog_lock:
            was_active = self._jog_active
            axis = self._jog_axis
            ref = self._jog_ref
            self._jog_active = False
        if was_active:
            self._force_stop_jog(axis, ref, stop_mode=2)


def main() -> int:
    robot_id = os.getenv("ROBOT_ID", "dsr01")
    rclpy.init()
    node = ManualControlWorker(robot_id=robot_id)
    executor = MultiThreadedExecutor(num_threads=4)
    executor.add_node(node)
    spin_thread = threading.Thread(target=executor.spin, daemon=True)
    spin_thread.start()

    try:
        for raw_line in sys.stdin:
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            req_id = payload.get("req_id")
            result = node.handle_command(payload)
            if req_id is not None:
                result["req_id"] = req_id
            print(json.dumps(result, ensure_ascii=False), flush=True)
    except KeyboardInterrupt:
        pass
    finally:
        node.stop_on_shutdown()
        executor.shutdown()
        node.destroy_node()
        rclpy.try_shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
