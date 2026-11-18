from fastapi import status

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
    """대시보드 로봇 제어 명령을 ROS2 브리지로 위임하는 서비스 레이어."""

    async def execute_command(
        self,
        command: str,
        target: str = "",
        *,
        call_timeout: float = 30.0,
    ) -> TaskExecuteResponse:
        try:
            result = await execute_task(
                command=command,
                target=target,
                call_timeout=call_timeout,
            )
        except RosServiceUnavailableError as exc:
            raise DashboardServiceError(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                str(exc),
            ) from exc
        except RosServiceTimeoutError as exc:
            raise DashboardServiceError(
                status.HTTP_504_GATEWAY_TIMEOUT,
                str(exc),
            ) from exc
        except RosBridgeError as exc:
            raise DashboardServiceError(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                str(exc),
            ) from exc

        if not result.success:
            raise DashboardServiceError(
                status.HTTP_502_BAD_GATEWAY,
                {
                    "error_code": result.error_code,
                    "message": result.message,
                },
            )

        return TaskExecuteResponse(
            success=result.success,
            error_code=result.error_code,
            message=result.message,
        )

    async def move_home(self) -> TaskExecuteResponse:
        return await self.execute_command("MOVE_HOME")

    async def move_to_scoop(self) -> TaskExecuteResponse:
        return await self.execute_command("MOVE_TO_SCOOP")

    async def move_cup_z(self) -> TaskExecuteResponse:
        return await self.execute_command("MOVE_CUP_Z")

    async def move_to_plate(self) -> TaskExecuteResponse:
        return await self.execute_command("MOVE_TO_PLATE")

    async def move_to_flavor(self, flavor: str) -> TaskExecuteResponse:
        return await self.execute_command("MOVE_TO_FLAVOR", target=flavor)

    async def grip_and_lift(self) -> TaskExecuteResponse:
        return await self.execute_command("GRIP_AND_LIFT")

    async def gripper_release(self) -> TaskExecuteResponse:
        return await self.execute_command("GRIPPER_RELEASE")

    async def gripper_grab(self) -> TaskExecuteResponse:
        return await self.execute_command("GRIPPER_GRAB")

    async def calibrate_cup_z(self) -> TaskExecuteResponse:
        return await self.execute_command("CALIBRATE_CUP_Z", call_timeout=190.0)


dashboard_service = DashboardService()
