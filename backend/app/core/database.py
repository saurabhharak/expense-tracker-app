from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager, contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from app.core.config import settings

# ── Async engine (FastAPI routes) ──
async_engine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_pre_ping=True,
    connect_args={
        "prepared_statement_cache_size": 0,  # PgBouncer compatibility
        "ssl": None,  # No SSL for container-to-container connections
    },
)
async_session_factory = async_sessionmaker(async_engine, expire_on_commit=False)

# ── Sync engine (Celery tasks) ──
sync_engine = create_engine(
    settings.SYNC_DATABASE_URL,
    pool_size=10,
    max_overflow=5,
    pool_pre_ping=True,
)
sync_session_factory = sessionmaker(sync_engine, expire_on_commit=False)

# ── Base for models ──
Base = declarative_base()


@asynccontextmanager
async def get_db_session(user_id: str | None = None) -> AsyncGenerator[AsyncSession, None]:
    """Async session with RLS context. Used by FastAPI routes."""
    async with async_session_factory() as session:
        async with session.begin():
            if user_id:
                await session.execute(
                    text("SET LOCAL app.current_user_id = :uid"),
                    {"uid": user_id},
                )
            yield session


@contextmanager
def sync_db_session(user_id: str | None = None):
    """Sync session with RLS context. Used by Celery tasks."""
    session: Session = sync_session_factory()
    try:
        session.begin()
        if user_id:
            session.execute(
                text("SET LOCAL app.current_user_id = :uid"),
                {"uid": user_id},
            )
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
