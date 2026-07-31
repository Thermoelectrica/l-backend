"""StickerType repository"""

from datetime import datetime
from itertools import groupby
from typing import List

import aiosql
from aiosql.queries import Queries

from app.config import settings
from app.constants import DEFAULT_MODIFIED_SINCE
from app.models.sticker_type import StickerTempRange, StickerType
from app.utils.async_wrapper import AsyncWrapper

# Load queries
_queries = aiosql.from_path("app/queries/sticker_type.sql", settings.db_driver)
queries: Queries = AsyncWrapper(_queries) if settings.db_driver == "psycopg2" else _queries  # type: ignore[assignment]


class StickerTypeRepository:
    """Repository for StickerType aggregate with child synchronization"""

    async def get_all(self, conn, modified_since: datetime = DEFAULT_MODIFIED_SINCE) -> List[StickerType]:
        """Get all sticker types with temperature ranges, optionally filtered by modification date"""
        # Get sticker types
        sticker_types = [row async for row in queries.get_sticker_types(conn, modified_since=modified_since)]
        if not sticker_types:
            return []
        temp_ranges_raw: list[dict] = [row async for row in queries.get_temp_ranges(conn)]
        temp_ranges = {
            key: [StickerTempRange(**row) for row in value]
            for key, value in groupby(temp_ranges_raw, lambda r: r["sticker_id"])
        }
        return [StickerType(**row, temp_ranges=temp_ranges.get(row["id"], [])) for row in sticker_types]
