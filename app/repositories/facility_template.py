"""FacilityTemplate repository"""

from datetime import datetime
from itertools import groupby
from typing import List

import aiosql
from aiosql.queries import Queries

from app.config import settings
from app.constants import DEFAULT_MODIFIED_SINCE
from app.models.facility_template import FacilityTemplate, FacilityTemplateEquipment
from app.utils.async_wrapper import AsyncWrapper

# Load queries
_queries = aiosql.from_path("app/queries/facility_template.sql", settings.db_driver)
queries: Queries = AsyncWrapper(_queries) if settings.db_driver == "psycopg2" else _queries  # type: ignore[assignment]


class FacilityTemplateRepository:
    """Repository for FacilityTemplate aggregate"""

    async def get_all(self, conn, modified_since: datetime = DEFAULT_MODIFIED_SINCE) -> List[FacilityTemplate]:
        """Get all facility templates with equipment templates, optionally filtered by modification date"""
        # Get all facility templates
        facility_templates = [
            row async for row in queries.get_all_facility_templates(conn, modified_since=modified_since)
        ]
        if not facility_templates:
            return []

        # Get all facility template equipment
        equipment_raw: list[dict] = [row async for row in queries.get_all_facility_template_equipment(conn)]
        equipment_by_template = {
            key: [FacilityTemplateEquipment(**row) for row in value]
            for key, value in groupby(equipment_raw, lambda r: r["facility_template_id"])
        }

        return [
            FacilityTemplate(**row, equipment_templates=equipment_by_template.get(row["id"], []))
            for row in facility_templates
        ]
