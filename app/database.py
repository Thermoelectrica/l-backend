"""Database connection pool management"""

from typing import Optional

import asyncpg
import psycopg2
import psycopg2.extras
from psycopg2 import pool

from app.config import settings
from app.utils.async_wrapper import AsyncConnectionWrapper

# Register UUID adapter for psycopg2
psycopg2.extras.register_uuid()

# Pools for both async and sync drivers
async_db_pool: Optional[asyncpg.Pool] = None
sync_db_pool: Optional[pool.ThreadedConnectionPool] = None


# === ASYNC IMPLEMENTATION (for regular FastAPI with asyncpg) ===


async def init_async_db_pool():
    """Initialize async database connection pool"""
    global async_db_pool
    if async_db_pool is None:
        async_db_pool = await asyncpg.create_pool(
            dsn=settings.get_database_url(), min_size=5, max_size=20, command_timeout=60
        )


async def close_async_db_pool():
    """Close async database connection pool"""
    global async_db_pool
    if async_db_pool:
        await async_db_pool.close()
        async_db_pool = None


# === SYNC IMPLEMENTATION (for serverless/mangum with psycopg2) ===


def init_sync_db_pool():
    """Initialize sync database connection pool (persists across warm invocations)"""
    global sync_db_pool
    if sync_db_pool is None:
        sync_db_pool = pool.ThreadedConnectionPool(
            minconn=1,  # Lower for serverless
            maxconn=10,
            dsn=settings.get_database_url(),
            cursor_factory=psycopg2.extras.RealDictCursor,
        )


def close_sync_db_pool():
    """Close sync database connection pool"""
    global sync_db_pool
    if sync_db_pool:
        sync_db_pool.closeall()
        sync_db_pool = None


# === UNIFIED INTERFACE ===


async def init_db_pool():
    """Initialize database pool based on driver setting"""
    if settings.db_driver == "asyncpg":
        await init_async_db_pool()
    else:
        init_sync_db_pool()  # No await - sync call


async def close_db_pool():
    """Close database pool based on driver setting"""
    if settings.db_driver == "asyncpg":
        await close_async_db_pool()
    else:
        close_sync_db_pool()  # No await - sync call


async def get_db_connection():
    """
    Unified dependency for getting database connection.
    Returns async or sync connection based on driver setting.

    In serverless environments where lifespan is disabled,
    this will initialize the pool on first request if needed.
    """
    if settings.db_driver == "asyncpg":
        # Async path
        global async_db_pool
        if async_db_pool is None:
            await init_async_db_pool()

        if async_db_pool is not None:
            async with async_db_pool.acquire() as connection:
                yield connection
    else:
        # Sync path - but wrapped in async function for FastAPI compatibility
        global sync_db_pool
        if sync_db_pool is None:
            init_sync_db_pool()  # No await

        if sync_db_pool is not None:
            conn = sync_db_pool.getconn()  # No await
            try:
                # Wrap connection to provide async-compatible transaction() method
                wrapped_conn = AsyncConnectionWrapper(conn)
                yield wrapped_conn
                # Auto-commit if no explicit transaction was used
                if not wrapped_conn._in_transaction:
                    conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                sync_db_pool.putconn(conn)  # No await


# Backwards compatibility - keep the old name
db_pool = async_db_pool
