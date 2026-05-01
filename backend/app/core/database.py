"""SQLAlchemy engine, session factory, and request-scoped session dependency."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from app.core.config import settings

engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    echo=settings.DEBUG,
)

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    class_=Session,
)


def get_db():
    """FastAPI dependency: yields a Session and guarantees it's closed.

    Used as `db: Session = Depends(get_db)` in route handlers.
    The yield/finally pattern is required because FastAPI dependencies that
    yield are treated as generators — code after the yield runs after the
    response is sent.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
