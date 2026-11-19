from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ALLOWED_FLAVORS = {"CHOCO", "STRAWBERRY", "VANILLA"}


class OrderCreateRequest(BaseModel):
    ice_cream_type: Literal["CUP", "SOFT"] = Field(default="CUP", description="아이스크림 유형 (CUP | SOFT)")
    cup_height_z: float | None = Field(default=None, ge=0.0, description="측정된 컵 높이 (mm)")
    cup_diameter: float | None = Field(default=None, ge=0.0, description="측정된 컵 직경 (mm)")
    scoops: list[str] = Field(default_factory=list, max_length=6, description="스쿱 맛 순서 목록 (CUP 주문 시 필수)")

    @field_validator("ice_cream_type", mode="before")
    @classmethod
    def normalize_type(cls, value: str) -> str:
        return str(value or "CUP").strip().upper()

    @field_validator("scoops")
    @classmethod
    def validate_scoops(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        for raw in value:
            flavor = raw.strip().upper()
            if flavor not in ALLOWED_FLAVORS:
                raise ValueError(f"지원하지 않는 맛입니다: {raw}")
            normalized.append(flavor)
        return normalized

    @model_validator(mode="after")
    def validate_type_requirements(self) -> "OrderCreateRequest":
        if self.ice_cream_type == "CUP" and not self.scoops:
            raise ValueError("컵 아이스크림(CUP) 주문에는 최소 1개 이상의 스쿱 맛이 필요합니다.")
        return self


class OrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_code: str
    ice_cream_type: str
    cup_height_z: float | None = None
    cup_diameter: float | None = None
    scoop_count: int
    scoops: list[str]
    order_status: str
    current_step: str | None = None
    progress_percent: float
    error_code: int | None = None
    error_message: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None


class MeasureRequest(BaseModel):
    measure_diameter: bool = Field(default=True, description="직경 측정 포함 여부")
    expected_diameter: float = Field(default=90.0, gt=0.0, description="기대 직경 (mm)")


class MeasureResultResponse(BaseModel):
    success: bool
    cup_available: bool = False
    measured_height_z: float = 0.0
    measured_diameter: float = 0.0
    error_code: int = 0
    message: str = ""
    measured_at: datetime | None = None
