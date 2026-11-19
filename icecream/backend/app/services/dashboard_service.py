import time

from fastapi import status

from db.database import SessionLocal
from models.action_log import DashboardActionLog
from repositories.action_log_repository import action_log_repository
from ros_bridge.execute_task_client import (
    RosBridgeError,
    RosServiceTimeoutError,
    RosServiceUnavailableError,
    execute_task,
)
from schemas.dashboard import TaskExecuteResponse


class DashboardServiceError(Exception):
    """대시보드 서비스 실행 중 발생한 오류."""

    def __init__(self, status_code: int, detail: str | dict) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(str(detail))


class DashboardService:
    """대시보드 로봇 제어 명령을 ROS2 브리지로 위임하고 실행 이력을 DB에 기록한다."""

    def _create_running_log(
        self,
        *,
        command: str,
        target: str,
        endpoint: str | None,
    ) -> int:
        with SessionLocal() as db:
            row = action_log_repository.create_running(
                db,
                command=command,
                target=target,
                endpoint=endpoint,
                source="DASHBOARD",
            )
            return row.id

    def _finish_log(
        self,
        log_id: int,
        *,
        log_status: str,
        http_status: int,
        error_code: int | None,
        message: str,
        duration_ms: int,
    ) -> None:
        with SessionLocal() as db:
            action_log_repository.finish(
                db,
                log_id,
                status=log_status,
                http_status=http_status,
                error_code=error_code,
                message=message,
                duration_ms=duration_ms,
            )

    def list_action_logs(self, *, limit: int = 50, source: str | None = None) -> list[DashboardActionLog]:
        with SessionLocal() as db:
            return action_log_repository.list_logs(db, limit=limit, source=source)

    def clear_action_logs(self, *, source: str | None = "DASHBOARD") -> int:
        with SessionLocal() as db:
            return action_log_repository.clear_logs(db, source=source)

    async def execute_command(
        self,
        command: str,
        target: str = "",
        *,
        endpoint: str | None = None,
        call_timeout: float = 30.0,
    ) -> TaskExecuteResponse:
        log_id = self._create_running_log(command=command, target=target, endpoint=endpoint)
        started = time.monotonic()

        try:
            result = await execute_task(
                command=command,
                target=target,
                call_timeout=call_timeout,
            )
        except RosServiceUnavailableError as exc:
            duration_ms = int((time.monotonic() - started) * 1000)
            self._finish_log(
                log_id,
                log_status="FAILED",
                http_status=status.HTTP_503_SERVICE_UNAVAILABLE,
                error_code=None,
                message=str(exc),
                duration_ms=duration_ms,
            )
            raise DashboardServiceError(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                str(exc),
            ) from exc
        except RosServiceTimeoutError as exc:
            duration_ms = int((time.monotonic() - started) * 1000)
            self._finish_log(
                log_id,
                log_status="FAILED",
                http_status=status.HTTP_504_GATEWAY_TIMEOUT,
                error_code=None,
                message=str(exc),
                duration_ms=duration_ms,
            )
            raise DashboardServiceError(
                status.HTTP_504_GATEWAY_TIMEOUT,
                str(exc),
            ) from exc
        except RosBridgeError as exc:
            duration_ms = int((time.monotonic() - started) * 1000)
            self._finish_log(
                log_id,
                log_status="FAILED",
                http_status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                error_code=None,
                message=str(exc),
                duration_ms=duration_ms,
            )
            raise DashboardServiceError(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                str(exc),
            ) from exc

        duration_ms = int((time.monotonic() - started) * 1000)

        if not result.success:
            self._finish_log(
                log_id,
                log_status="FAILED",
                http_status=status.HTTP_502_BAD_GATEWAY,
                error_code=result.error_code,
                message=result.message,
                duration_ms=duration_ms,
            )
            raise DashboardServiceError(
                status.HTTP_502_BAD_GATEWAY,
                {
                    "error_code": result.error_code,
                    "message": result.message,
                },
            )

        self._finish_log(
            log_id,
            log_status="SUCCESS",
            http_status=status.HTTP_200_OK,
            error_code=result.error_code,
            message=result.message,
            duration_ms=duration_ms,
        )

        return TaskExecuteResponse(
            success=result.success,
            error_code=result.error_code,
            message=result.message,
        )

    async def move_home(self) -> TaskExecuteResponse:
        return await self.execute_command("MOVE_HOME", endpoint="/home")

    async def move_to_scoop(self) -> TaskExecuteResponse:
        return await self.execute_command("MOVE_TO_SCOOP", endpoint="/move-to-scoop")

    async def move_cup_z(self) -> TaskExecuteResponse:
        return await self.execute_command("MOVE_CUP_Z", endpoint="/move-cup-z")

    async def move_cup_hold(self) -> TaskExecuteResponse:
        return await self.execute_command("MOVE_CUP_HOLD", endpoint="/move-cup-hold")

    async def move_cup_middle(self) -> TaskExecuteResponse:
        return await self.execute_command("MOVE_CUP_MIDDLE", endpoint="/move-cup-middle")

    async def move_cup_sprial(self) -> TaskExecuteResponse:
        return await self.execute_command("MOVE_CUP_SPRIAL", endpoint="/move-cup-sprial")

    async def move_to_plate(self) -> TaskExecuteResponse:
        return await self.execute_command("MOVE_TO_PLATE", endpoint="/move-to-plate")

    async def move_to_flavor(self, flavor: str) -> TaskExecuteResponse:
        return await self.execute_command(
            "MOVE_TO_FLAVOR",
            target=flavor,
            endpoint="/move-to-flavor",
        )

    async def grip_and_lift(self) -> TaskExecuteResponse:
        return await self.execute_command("GRIP_AND_LIFT", endpoint="/grip-and-lift")

    async def gripper_release(self) -> TaskExecuteResponse:
        return await self.execute_command("GRIPPER_RELEASE", endpoint="/gripper-release")

    async def gripper_grab(self) -> TaskExecuteResponse:
        return await self.execute_command("GRIPPER_GRAB", endpoint="/gripper-grab")

    async def gripper_cup(self) -> TaskExecuteResponse:
        return await self.execute_command("GRIPPER_CUP", endpoint="/gripper-cup")

    async def calibrate_cup_z(self) -> TaskExecuteResponse:
        return await self.execute_command(
            "CALIBRATE_CUP_Z",
            endpoint="/calibrate-cup-z",
            call_timeout=190.0,
        )

    async def push_cup_corner(self) -> TaskExecuteResponse:
        return await self.execute_command(
            "PUSH_CUP_CORNER",
            endpoint="/push-cup-corner",
            call_timeout=150.0,
        )

    async def calibrate_cup_diameter(self) -> TaskExecuteResponse:
        return await self.execute_command(
            "CALIBRATE_CUP_DIAMETER",
            endpoint="/calibrate-cup-diameter",
            call_timeout=150.0,
        )


dashboard_service = DashboardService()
