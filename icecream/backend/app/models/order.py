from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from db.database import Base


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Order(Base):
    """키오스크 주문 및 로봇 제조 진행 상태 테이블."""

    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    ice_cream_type: Mapped[str] = mapped_column(String(20), nullable=False, default="CUP")
    cup_height_z: Mapped[float | None] = mapped_column(Float, nullable=True)
    cup_diameter: Mapped[float | None] = mapped_column(Float, nullable=True)
    scoop_count: Mapped[int] = mapped_column(Integer, nullable=False)
    scoops: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    order_status: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        default="PENDING",
        index=True,
    )
    current_step: Mapped[str | None] = mapped_column(String(64), nullable=True)
    progress_percent: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    error_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utc_now,
        index=True,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
