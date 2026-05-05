from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from config import get_settings


def get_echo_setting() -> bool | str:
    value = get_settings().model_config.get("env_file", "")
    # Read ORM_ECHO_SQL directly since it's not in Settings yet
    import os
    raw = os.getenv("ORM_ECHO_SQL", "false").strip().lower()
    if raw == "debug":
        return "debug"
    return raw in {"1", "true", "yes", "on"}


def get_database_url() -> str:
    import os
    postgres_dsn = os.getenv("POSTGRES_DSN", "").strip()
    if not postgres_dsn:
        raise ValueError("Missing required environment variable: POSTGRES_DSN")
    if postgres_dsn.startswith("postgresql://"):
        return postgres_dsn.replace("postgresql://", "postgresql+psycopg://", 1)
    return postgres_dsn


def create_db_engine() -> Engine:
    return create_engine(
        get_database_url(),
        echo = get_echo_setting(),
        pool_pre_ping=True,
    )


engine: Engine = create_db_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


@contextmanager
def get_session() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
