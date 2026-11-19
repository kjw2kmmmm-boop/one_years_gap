from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.order import Order


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class OrderRepository:
    """orders 테이블 CRUD 및 상태 전이 담당 리포지토리."""

    def generate_order_code(self, db: Session) -> str:
        """오늘 날짜 기준 충돌 없는 주문 번호(예: ICE-20261118-001)를 생성한다."""
        date_prefix = _utc_now().strftime("%Y%m%d")
        prefix = f"ICE-{date_prefix}-"
        stmt = (
            select(Order.order_code)
            .where(Order.order_code.like(f"{prefix}%"))
            .order_by(Order.id.desc())
            .limit(1)
        )
        last_code = db.scalar(stmt)
        next_seq = 1
        if last_code and last_code.startswith(prefix):
            suffix = last_code[len(prefix) :]
            if suffix.isdigit():
                next_seq = int(suffix) + 1
        return f"{prefix}{next_seq:03d}"

    def create(
        self,
        db: Session,
        *,
        scoops: list[str],
        ice_cream_type: str = "CUP",
        cup_height_z: float | None = None,
        cup_diameter: float | None = None,
        order_code: str | None = None,
    ) -> Order:
        normalized_scoops = [s.strip().upper() for s in scoops if s.strip()]
        code = order_code or self.generate_order_code(db)
        order = Order(
            order_code=code,
            ice_cream_type=ice_cream_type.strip().upper(),
            cup_height_z=cup_height_z,
            cup_diameter=cup_diameter,
            scoop_count=len(normalized_scoops),
            scoops=normalized_scoops,
            order_status="PENDING",
            progress_percent=0.0,
        )
        db.add(order)
        db.commit()
        db.refresh(order)
        return order

    def get_by_id(self, db: Session, order_id: int) -> Order | None:
        return db.get(Order, order_id)

    def get_by_code(self, db: Session, order_code: str) -> Order | None:
        stmt = select(Order).where(Order.order_code == order_code)
        return db.scalar(stmt)

    def list_orders(
        self,
        db: Session,
        *,
        limit: int = 50,
        offset: int = 0,
        status: str | None = None,
    ) -> list[Order]:
        stmt = select(Order)
        if status:
            statuses = [s.strip().upper() for s in status.split(",") if s.strip()]
            if len(statuses) == 1:
                stmt = stmt.where(Order.order_status == statuses[0])
            elif statuses:
                stmt = stmt.where(Order.order_status.in_(statuses))
        stmt = stmt.order_by(Order.created_at.desc(), Order.id.desc()).offset(offset).limit(limit)
        return list(db.scalars(stmt).all())

    def mark_started(
        self,
        db: Session,
        order_code: str,
        *,
        current_step: str = "STARTING",
    ) -> Order | None:
        order = self.get_by_code(db, order_code)
        if order is None:
            return None
        order.order_status = "IN_PROGRESS"
        order.current_step = current_step
        if order.started_at is None:
            order.started_at = _utc_now()
        db.commit()
        db.refresh(order)
        return order

    def update_progress(
        self,
        db: Session,
        order_code: str,
        *,
        order_status: str,
        current_step: str,
        progress_percent: float,
    ) -> Order | None:
        order = self.get_by_code(db, order_code)
        if order is None:
            return None
        order.order_status = order_status
        order.current_step = current_step
        order.progress_percent = float(progress_percent)
        if order.started_at is None:
            order.started_at = _utc_now()
        db.commit()
        db.refresh(order)
        return order

    def mark_completed(
        self,
        db: Session,
        order_code: str,
        *,
        current_step: str = "COMPLETED",
    ) -> Order | None:
        order = self.get_by_code(db, order_code)
        if order is None:
            return None
        order.order_status = "COMPLETED"
        order.current_step = current_step
        order.progress_percent = 100.0
        order.error_code = 0
        order.error_message = None
        order.completed_at = _utc_now()
        db.commit()
        db.refresh(order)
        return order

    def mark_failed(
        self,
        db: Session,
        order_code: str,
        *,
        error_code: int | None,
        error_message: str,
        status: str = "FAILED",
    ) -> Order | None:
        order = self.get_by_code(db, order_code)
        if order is None:
            return None
        order.order_status = status
        order.error_code = error_code
        order.error_message = error_message
        order.completed_at = _utc_now()
        db.commit()
        db.refresh(order)
        return order


order_repository = OrderRepository()
