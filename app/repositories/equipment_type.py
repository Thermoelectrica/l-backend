"""EquipmentType repository"""

from datetime import datetime
from itertools import groupby
from typing import List, Optional

import aiosql
from aiosql.queries import Queries

from app.config import settings
from app.constants import DEFAULT_MODIFIED_SINCE
from app.models.equipment_type import ControlPointTemplate, EquipmentType
from app.utils.async_wrapper import AsyncWrapper

# Load queries
_queries = aiosql.from_path("app/queries/equipment_type.sql", settings.db_driver)
queries: Queries = AsyncWrapper(_queries) if settings.db_driver == "psycopg2" else _queries  # type: ignore[assignment]


class EquipmentTypeRepository:
    """Repository for EquipmentType aggregate with child synchronization"""

    async def get_all(self, conn, modified_since: datetime = DEFAULT_MODIFIED_SINCE) -> List[EquipmentType]:
        """Get all equipment types with control point templates, optionally filtered by modification date"""
        # Get all equipment types
        equipment_types = [row async for row in queries.get_all_equipment_types(conn, modified_since=modified_since)]
        if not equipment_types:
            return []

        # Get all control point templates
        templates_raw: list[dict] = [row async for row in queries.get_all_control_point_templates(conn)]
        templates_by_type = {
            key: [ControlPointTemplate(**row) for row in value]
            for key, value in groupby(templates_raw, lambda r: r["equipment_type_id"])
        }

        return [
            EquipmentType(**row, control_point_templates=templates_by_type.get(row["id"], []))
            for row in equipment_types
        ]

    async def get_by_id(self, conn, equipment_type_id: int) -> Optional[EquipmentType]:
        """Get equipment type by ID with control point templates"""
        # Get equipment type
        equipment_type_row = await queries.get_by_id(conn, id=equipment_type_id)
        if not equipment_type_row:
            return None

        # Get control point templates
        template_rows = [
            row async for row in queries.get_control_point_templates(conn, equipment_type_id=equipment_type_id)
        ]
        templates = [ControlPointTemplate(**row) for row in template_rows]

        return EquipmentType(**equipment_type_row, control_point_templates=templates)

    async def save(self, conn, equipment_type: EquipmentType) -> EquipmentType:
        """Save equipment type with child synchronization (must be called within transaction)"""
        # Upsert equipment type
        await queries.upsert_equipment_type(conn, id=equipment_type.id, name=equipment_type.name)

        # Synchronize control point templates
        await self._sync_templates(conn, equipment_type.id, equipment_type.control_point_templates)

        # Return updated aggregate
        result = await self.get_by_id(conn, equipment_type.id)
        if result is None:
            raise ValueError(f"EquipmentType {equipment_type.id} not found after save")
        return result

    async def delete(self, conn, equipment_type_id: int) -> bool:
        """Delete equipment type (must be called within transaction)"""
        result = await queries.delete_equipment_type(conn, id=equipment_type_id)
        # aiosql returns status string like "DELETE 1" for affected rows
        return result is not None and "0" not in result

    async def _sync_templates(self, conn, equipment_type_id: int, templates: list[ControlPointTemplate]):
        """Synchronize control point templates: match by ID, add new, delete removed"""
        # Get existing template IDs
        existing_rows = [row async for row in queries.get_template_ids(conn, equipment_type_id=equipment_type_id)]
        existing_ids = {row["id"] for row in existing_rows}

        incoming_ids = {t.id for t in templates}

        # Update or insert
        for template in templates:
            await queries.upsert_template(
                conn,
                id=template.id,
                equipment_type_id=equipment_type_id,
                name=template.name,
                short_name=template.short_name,
                default_sticker_id=template.default_sticker_id,
            )

        # Delete removed templates
        to_delete = existing_ids - incoming_ids
        for template_id in to_delete:
            await queries.delete_template(conn, id=template_id)
