"""InspectionSchedule repository"""

from datetime import datetime
from typing import List

import aiosql
from aiosql.queries import Queries

from app.config import settings
from app.constants import DEFAULT_MODIFIED_SINCE
from app.models.inspection_schedule import InspectionSchedule
from app.utils.async_wrapper import AsyncWrapper

# Load queries
_queries = aiosql.from_path("app/queries/inspection_schedule.sql", settings.db_driver)
queries: Queries = AsyncWrapper(_queries) if settings.db_driver == "psycopg2" else _queries  # type: ignore[assignment]


class InspectionScheduleRepository:
    """Repository for InspectionSchedule aggregate"""

    async def get_all(self, conn, modified_since: datetime = DEFAULT_MODIFIED_SINCE) -> List[InspectionSchedule]:
        """Get all inspection schedules, optionally filtered by modification date"""
        schedules = [
            InspectionSchedule(**row)
            async for row in queries.get_all_inspection_schedules(conn, modified_since=modified_since)
        ]
        return schedules
