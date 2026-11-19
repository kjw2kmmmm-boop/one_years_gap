from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TaskExecuteResponse(BaseModel):
    success: bool
    error_code: int
    message: str


HomeMoveResponse = TaskExecuteResponse


class ActionLogResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source: str
    order_id: int | None = None
    command: str
    target: str | None = None
    endpoint: str | None = None
    status: str
    http_status: int | None = None
    error_code: int | None = None
    message: str | None = None
    duration_ms: int | None = None
    executed_at: datetime


class MoveToFlavorRequest(BaseModel):
    flavor: str = Field(..., min_length=1, description="이동할 아이스크림 맛 (예: CHOCO, STRAWBERRY)")


class TelemetrySnapshot(BaseModel):
    connected: bool = False
    timestamp: float = 0.0
    robot_mode: str = "MANUAL"
    is_emergency_stopped: bool = False
    is_robot_moving: bool = False
    current_tcp_pose: list[float] = Field(default_factory=lambda: [0.0] * 6)
    current_joint_angles: list[float] = Field(default_factory=lambda: [0.0] * 6)
    joint_torques: list[float] = Field(default_factory=lambda: [0.0] * 6)
    tool_force_z: float = 0.0
    system_state: str = "IDLE"
    current_order_id: str = ""
    current_order_progress: float = 0.0
    latest_cup_height_z: float = 0.0
    cup_stock_warning: bool = False
    active_error_code: int = 0
