from collections.abc import Generator
import os
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

_ICECREAM_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_DB_PATH = _ICECREAM_ROOT / "data" / "icecream.db"


def get_database_url() -> str:
    """SQLite 기본 경로 또는 DATABASE_URL 환경변수를 반환한다."""
    env_url = os.getenv("DATABASE_URL")
    if env_url:
        return env_url
    _DEFAULT_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{_DEFAULT_DB_PATH}"


class Base(DeclarativeBase):
    """SQLAlchemy ORM 기본 클래스."""


def _configure_sqlite_pragmas(dbapi_connection, _connection_record) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()


DATABASE_URL = get_database_url()
_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, connect_args=_connect_args)
if DATABASE_URL.startswith("sqlite"):
    event.listen(engine, "connect", _configure_sqlite_pragmas)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def init_db() -> None:
    """등록된 ORM 모델 기준으로 테이블을 생성한다."""
    import models  # noqa: F401 - Base.metadata에 모델 등록

    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    """FastAPI 요청 단위 DB 세션을 제공한다."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
