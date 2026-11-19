from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from models.action_log import DashboardActionLog


class ActionLogRepository:
    """dashboard_action_logs 테이블 CRUD 담당 리포지토리."""

    def create_running(
        self,
        db: Session,
        *,
        command: str,
        target: str = "",
        endpoint: str | None = None,
        source: str = "DASHBOARD",
        order_id: int | None = None,
    ) -> DashboardActionLog:
        log = DashboardActionLog(
            source=source,
            order_id=order_id,
            command=command,
            target=target or None,
            endpoint=endpoint,
            status="RUNNING",
        )
        db.add(log)
        db.commit()
        db.refresh(log)
        return log

    def finish(
        self,
        db: Session,
        log_id: int,
        *,
        status: str,
        http_status: int | None = None,
        error_code: int | None = None,
        message: str | None = None,
        duration_ms: int | None = None,
    ) -> DashboardActionLog | None:
        log = db.get(DashboardActionLog, log_id)
        if log is None:
            return None
        log.status = status
        log.http_status = http_status
        log.error_code = error_code
        log.message = message
        log.duration_ms = duration_ms
        db.commit()
        db.refresh(log)
        return log

    def list_logs(
        self,
        db: Session,
        *,
        limit: int = 50,
        offset: int = 0,
        source: str | None = None,
    ) -> list[DashboardActionLog]:
        stmt = select(DashboardActionLog)
        if source:
            stmt = stmt.where(DashboardActionLog.source == source.strip().upper())
        stmt = (
            stmt.order_by(DashboardActionLog.executed_at.desc(), DashboardActionLog.id.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(db.scalars(stmt).all())

    def clear_logs(self, db: Session, *, source: str | None = None) -> int:
        stmt = delete(DashboardActionLog)
        if source:
            stmt = stmt.where(DashboardActionLog.source == source.strip().upper())
        result = db.execute(stmt)
        db.commit()
        return int(result.rowcount or 0)


action_log_repository = ActionLogRepository()
