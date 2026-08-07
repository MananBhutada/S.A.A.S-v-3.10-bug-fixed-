"""
db/session.py — Database session management
Supports PostgreSQL (production) and SQLite (development/testing)
"""
from __future__ import annotations
import os
import logging
from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from contextlib import contextmanager
from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger("DB")

BASE_DIR  = Path(__file__).parent.parent
SQLITE_URL = f"sqlite:///{BASE_DIR}/data/saas.db"

def get_db_url() -> str:
    pg = os.getenv("DATABASE_URL", "").strip()
    if pg:
        log.info("Using PostgreSQL: %s", pg.split("@")[-1])
        return pg
    log.info("DATABASE_URL not set — using SQLite: %s", SQLITE_URL)
    return SQLITE_URL

_engine = None
_SessionLocal = None

def get_engine():
    global _engine
    if _engine is None:
        url = get_db_url()
        kwargs = {}
        if url.startswith("sqlite"):
            kwargs["check_same_thread"] = False
        else:
            kwargs["pool_size"]    = 5
            kwargs["max_overflow"] = 10
            kwargs["pool_pre_ping"] = True
        _engine = create_engine(url, connect_args=kwargs if url.startswith("sqlite") else {}, **({} if url.startswith("sqlite") else kwargs))
    return _engine

def get_session_factory():
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=get_engine())
    return _SessionLocal

@contextmanager
def get_session() -> Session:
    factory = get_session_factory()
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

def init_db():
    """Create all tables if they don't exist."""
    from db.models import Base
    Base.metadata.create_all(bind=get_engine())
    log.info("Database tables initialised")

def check_db_health() -> dict:
    try:
        with get_session() as s:
            s.execute(text("SELECT 1"))
        return {"status": "healthy", "url": get_db_url().split("@")[-1]}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}
