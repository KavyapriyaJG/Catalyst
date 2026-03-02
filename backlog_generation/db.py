from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

import backlog_generation.utils as utils


def get_echo_setting() -> bool | str:
    value = utils.get_from_env("ORM_ECHO_SQL", "false").strip().lower()
    if value == "debug":
        return "debug"
    return value in {"1", "true", "yes", "on"}


def get_database_url() -> str:
    postgres_dsn = utils.get_from_env("POSTGRES_DSN")
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
