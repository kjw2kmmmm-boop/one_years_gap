from typing import Literal

from pydantic import BaseModel, Field


class ManualStepRequest(BaseModel):
    space: Literal["task", "joint"] = "task"
    axis: int = Field(..., ge=0, le=5, description="Task: 0=X..5=Rz / Joint: 0=J1..5=J6")
    delta: float = Field(..., description="이동량 (mm 또는 deg)")
    move_reference: int = Field(default=0, ge=0, le=1, description="0=BASE, 1=TOOL")
    speed_pct: float = Field(default=25.0, ge=1.0, le=50.0, description="수동 이동 속도 비율 (%)")


class ManualStopRequest(BaseModel):
    stop_mode: int = Field(default=1, ge=0, le=3, description="0=QSTOP_STO, 1=QSTOP, 2=SSTO, 3=HOLD")


class ManualSpeedRequest(BaseModel):
    speed: int = Field(..., ge=1, le=100, description="전체 동작 속도 배율 (1~100%)")


class ManualModeRequest(BaseModel):
    robot_mode: int = Field(..., ge=0, le=2, description="0=MANUAL, 1=AUTONOMOUS, 2=MEASURE")


class ManualControlResponse(BaseModel):
    success: bool
    message: str
