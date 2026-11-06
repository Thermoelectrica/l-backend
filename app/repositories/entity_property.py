"""EntityProperty repository"""

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

import aiosql
from aiosql.queries import Queries

from app.config import settings
from app.constants import DEFAULT_MODIFIED_SINCE
from app.exceptions import ConcurrentModificationError
from app.models import ConflictDetail, ConflictError
from app.models.entity_property import (
    EntityProperty,
    EntityPropertyListResponse,
)
from app.utils.async_wrapper import AsyncWrapper
from app.utils.datetime_utils import truncate_to_milliseconds

# Load queries with configurable driver
_queries = aiosql.from_path("app/queries/entity_property.sql", settings.db_driver)
queries: Queries = AsyncWrapper(_queries) if settings.db_driver == "psycopg2" else _queries  # type: ignore[assignment]


class EntityPropertyRepository:
    """Repository for EntityProperty aggregate with optimistic concurrency control.

    There is no delete: the table has no is_deleted column, because an absent row and a row with
    every attribute NULL describe the same state. Clearing a property means setting it to NULL.
    """

    async def get_by_id(self, conn, entity_id: UUID) -> Optional[EntityProperty]:
        """Get entity property by entity ID, or None if the entity has no row yet"""
        properties_row = await queries.get_by_id(conn, id=entity_id)
        if not properties_row:
            return None
        return EntityProperty(**properties_row)

    async def get_all(self, conn, modified_since: datetime = DEFAULT_MODIFIED_SINCE) -> EntityPropertyListResponse:
        """Get all entity properties, optionally filtered by modification date"""
        properties_rows = [row async for row in queries.get_all_entity_property(conn, modified_since=modified_since)]
        properties_list = [EntityProperty(**row) for row in properties_rows]
        return EntityPropertyListResponse(items=properties_list)

    async def get_by_plant_id(
        self, conn, plant_id: UUID, modified_since: datetime = DEFAULT_MODIFIED_SINCE
    ) -> list[EntityProperty]:
        """Get all entity properties for a plant, optionally filtered by modification date.

        Covers all three entity types: the plant's own row, its facilities and their equipment.
        Only rows that actually exist are returned: entities without a property row have nothing
        for the client to sync.
        """
        properties_rows = [
            row async for row in queries.get_by_plant_id(conn, plant_id=plant_id, modified_since=modified_since)
        ]
        return [EntityProperty(**row) for row in properties_rows]

    async def save(self, conn, properties: EntityProperty, force: bool = False) -> EntityProperty:
        """
        Save entity property with optimistic concurrency control.
        Must be called within transaction.

        Args:
            conn: Database connection
            properties: Entity property to save
            force: If True, ignore server_modified_at validation

        Raises:
            ConcurrentModificationError: If concurrent modification detected (force=False)
        """
        entity_id = properties.entity_id

        # Get current state if exists
        current = await self.get_by_id(conn, entity_id)

        # New server_modified_at timestamp
        new_server_modified_at = datetime.now(timezone.utc)

        if current and not (force or settings.disable_optimistic_locking):
            # Validate server_modified_at for existing properties
            assert current.server_modified_at is not None
            if properties.server_modified_at is None:
                raise ConcurrentModificationError(
                    ConflictError(
                        message="server_modified_at is required for updating existing entity property",
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
                        message="Entity property was modified by another client",
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

        # Upsert entity property
        await queries.upsert_entity_property(
            conn,
            entity_id=entity_id,
            entity_type=properties.entity_type.value,
            inspection_schedule_id=properties.inspection_schedule_id,
            server_modified_at=new_server_modified_at,
        )

        # Return updated aggregate
        result = await self.get_by_id(conn, entity_id)
        if result is None:
            raise ValueError(f"Entity property for {entity_id} not found after save")
        return result
