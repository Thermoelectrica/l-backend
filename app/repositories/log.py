"""Log repository"""

import json

import aiosql
from aiosql.queries import Queries

from app.config import settings
from app.models.log import LogEntry
from app.utils.async_wrapper import AsyncWrapper

# Load queries with configurable driver
_queries = aiosql.from_path("app/queries/log.sql", settings.db_driver)
queries: Queries = AsyncWrapper(_queries) if settings.db_driver == "psycopg2" else _queries  # type: ignore[assignment]


class LogRepository:
    """Repository for Log (append-only)"""

    async def insert_batch(self, conn, logs: list[LogEntry]) -> int:
        """Insert multiple log entries"""
        count = 0
        for log in logs:
            await queries.insert_one(
                conn,
                logged_at=log.logged_at,
                plant_id=log.plant_id,
                inspector_id=log.inspector_id,
                entity_id=log.entity_id,
                entity_type=log.entity_type.value,
                op=log.op.value,
                data=json.dumps(log.data) if log.data else None,
                message=log.message,
            )
            count += 1
        return count
