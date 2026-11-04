"""EquipmentProperty repository"""

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

import aiosql
from aiosql.queries import Queries

from app.config import settings
from app.constants import DEFAULT_MODIFIED_SINCE
from app.exceptions import ConcurrentModificationError
from app.models import ConflictDetail, ConflictError
from app.models.equipment_property import (
    EquipmentProperty,
    EquipmentPropertyListResponse,
)
from app.utils.async_wrapper import AsyncWrapper
from app.utils.datetime_utils import truncate_to_milliseconds

# Load queries with configurable driver
_queries = aiosql.from_path("app/queries/equipment_property.sql", settings.db_driver)
queries: Queries = AsyncWrapper(_queries) if settings.db_driver == "psycopg2" else _queries  # type: ignore[assignment]


class EquipmentPropertyRepository:
    """Repository for EquipmentProperty aggregate with optimistic concurrency control.

    There is no delete: the table has no is_deleted column, because an absent row and a row with
    every attribute NULL describe the same state. Clearing a property means setting it to NULL.
    """

    async def get_by_id(self, conn, equipment_id: UUID) -> Optional[EquipmentProperty]:
        """Get equipment property by equipment ID, or None if the equipment has no row yet"""
        properties_row = await queries.get_by_id(conn, id=equipment_id)
        if not properties_row:
            return None
        return EquipmentProperty(**properties_row)

    async def get_all(self, conn, modified_since: datetime = DEFAULT_MODIFIED_SINCE) -> EquipmentPropertyListResponse:
        """Get all equipment properties, optionally filtered by modification date"""
        properties_rows = [
            row async for row in queries.get_all_equipment_property(conn, modified_since=modified_since)
        ]
        properties_list = [EquipmentProperty(**row) for row in properties_rows]
        return EquipmentPropertyListResponse(items=properties_list)

    async def get_by_plant_id(
        self, conn, plant_id: UUID, modified_since: datetime = DEFAULT_MODIFIED_SINCE
    ) -> list[EquipmentProperty]:
        """Get all equipment properties for a plant, optionally filtered by modification date.

        Only rows that actually exist are returned: equipment without a property row has nothing
        for the client to sync.
        """
        properties_rows = [
            row async for row in queries.get_by_plant_id(conn, plant_id=plant_id, modified_since=modified_since)
        ]
        return [EquipmentProperty(**row) for row in properties_rows]

    async def save(self, conn, properties: EquipmentProperty, force: bool = False) -> EquipmentProperty:
        """
        Save equipment property with optimistic concurrency control.
        Must be called within transaction.

        Args:
            conn: Database connection
            properties: Equipment property to save
            force: If True, ignore server_modified_at validation

        Raises:
            ConcurrentModificationError: If concurrent modification detected (force=False)
        """
        equipment_id = properties.equipment_id

        # Get current state if exists
        current = await self.get_by_id(conn, equipment_id)

        # New server_modified_at timestamp
        new_server_modified_at = datetime.now(timezone.utc)

        if current and not (force or settings.disable_optimistic_locking):
            # Validate server_modified_at for existing properties
            assert current.server_modified_at is not None
            if properties.server_modified_at is None:
                raise ConcurrentModificationError(
                    ConflictError(
                        message="server_modified_at is required for updating existing equipment property",
                        server_modified_at=current.server_modified_at,
                        conflicts=[
                            ConflictDetail(
                                field="server_modified_at",
                                message="Missing server_modified_at in request",
                            )
                        ],
                    )
                )

            if truncate_to_milliseconds(properties.server_modified_at) != truncate_to_milliseconds(
                current.server_modified_at
            ):
                raise ConcurrentModificationError(
                    ConflictError(
                        message="Equipment property was modified by another client",
                        server_modified_at=current.server_modified_at,
                        client_modified_at=properties.server_modified_at,
                        conflicts=[
                            ConflictDetail(
                                field="server_modified_at",
                                message="Timestamp mismatch",
                                server_value=current.server_modified_at.isoformat(),
                                client_value=properties.server_modified_at.isoformat(),
                            )
                        ],
                    )
                )

        # Upsert equipment property
        await queries.upsert_equipment_property(
            conn,
            equipment_id=equipment_id,
            inspection_schedule_id=properties.inspection_schedule_id,
            server_modified_at=new_server_modified_at,
        )

        # Return updated aggregate
        result = await self.get_by_id(conn, equipment_id)
        if result is None:
            raise ValueError(f"Equipment property for {equipment_id} not found after save")
        return result
