"""
app/database/database.py
------------------------
Async SQLAlchemy engine, session factory, and FastAPI dependency.

Design choices
--------------
- asyncpg driver (postgresql+asyncpg://) for non-blocking I/O.
- NullPool in production to play nicely with pgBouncer / serverless.
- AsyncSessionLocal is an async context manager — callers use
  `async with get_db() as session:` or the FastAPI Depends helper.
- A synchronous engine is created alongside the async one exclusively
  for Alembic, which cannot yet use async connections.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Declarative base  — all ORM models inherit from this
# ---------------------------------------------------------------------------
class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Async engine
# ---------------------------------------------------------------------------
def _build_async_engine() -> AsyncEngine:
    kwargs: dict = {
        "echo": settings.DATABASE_ECHO,
        "future": True,
    }
    if settings.DATABASE_URL.startswith("sqlite"):
        kwargs["connect_args"] = {"timeout": 30}
        return create_async_engine(settings.DATABASE_URL, **kwargs)

    # Use NullPool in production so every request gets a fresh connection
    # from pgBouncer rather than keeping connections parked in the app.
    if settings.is_production:
        kwargs["poolclass"] = NullPool
    else:
        # Dev: small pool, recycle connections every 30 min
        kwargs["pool_size"] = 5
        kwargs["max_overflow"] = 10
        kwargs["pool_recycle"] = 1800
        kwargs["pool_pre_ping"] = True

    return create_async_engine(settings.DATABASE_URL, **kwargs)


async_engine: AsyncEngine = _build_async_engine()

# Session factory — expire_on_commit=False prevents lazy-load errors after commit
AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


# ---------------------------------------------------------------------------
# Synchronous engine for Alembic only
# ---------------------------------------------------------------------------
def get_sync_url() -> str:
    """Convert asyncpg URL to psycopg2 URL for Alembic."""
    if settings.DATABASE_URL.startswith("sqlite+aiosqlite"):
        return settings.DATABASE_URL.replace("sqlite+aiosqlite", "sqlite")
    return settings.DATABASE_URL.replace(
        "postgresql+asyncpg://", "postgresql+psycopg2://"
    ).replace(
        "postgresql://", "postgresql+psycopg2://"
    )


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Yield an AsyncSession, automatically rolling back on exception
    and closing the session when done.

    Usage in a route::

        @router.get("/")
        async def endpoint(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ---------------------------------------------------------------------------
# Context-manager variant (used by workers / scripts outside FastAPI)
# ---------------------------------------------------------------------------
@asynccontextmanager
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Async context manager for use outside FastAPI dependency injection.

    Usage::

        async with db_session() as db:
            result = await db.execute(select(User))
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ---------------------------------------------------------------------------
# Startup / shutdown helpers called from app/main.py lifespan
# ---------------------------------------------------------------------------
async def connect_db() -> None:
    """Verify the database is reachable at startup."""
    try:
        async with async_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        if settings.DATABASE_URL.startswith("sqlite"):
            async with async_engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
                columns = {
                    row[1]
                    for row in (await conn.execute(text("PRAGMA table_info(documents)"))).all()
                }
                if "processing_started_at" not in columns:
                    await conn.execute(text(
                        "ALTER TABLE documents ADD COLUMN processing_started_at DATETIME"
                    ))
                if "processing_completed_at" not in columns:
                    await conn.execute(text(
                        "ALTER TABLE documents ADD COLUMN processing_completed_at DATETIME"
                    ))
                await conn.execute(text(
                    "UPDATE documents SET status = 'uploaded' WHERE status = 'pending'"
                ))
                await conn.execute(text(
                    "UPDATE documents SET status = 'ready' WHERE status = 'completed'"
                ))
        logger.info("Database connection verified")
    except Exception as exc:
        logger.error(
            "Database connection failed — check DATABASE_URL",
            extra={"error": str(exc)},
        )
        # Do not raise — allow the app to start even if DB is temporarily down.
        # Health endpoint will report the failure.
        return


async def disconnect_db() -> None:
    """Dispose the connection pool gracefully at shutdown."""
    await async_engine.dispose()
    logger.info("Database connection pool disposed")


async def check_db_health() -> str:
    """
    Return "ok" or an error string.
    Used by GET /admin/health.
    """
    try:
        async with async_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return "ok"
    except Exception as exc:
        return f"error: {exc}"
