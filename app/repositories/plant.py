"""Plant repository"""

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

import aiosql
from aiosql.queries import Queries

from app.config import settings
from app.constants import DEFAULT_MODIFIED_SINCE
from app.models.plant import Facility, Plant, PlantListItem, PlantListResponse
from app.utils.async_wrapper import AsyncWrapper
from app.utils.db_utils import CollectionConfig, OptimisticLockingValidator

# Load queries from single file
_queries = aiosql.from_path("app/queries/plant.sql", settings.db_driver)
queries: Queries = AsyncWrapper(_queries) if settings.db_driver == "psycopg2" else _queries  # type: ignore[assignment]


class PlantRepository:
    """Repository for Plant aggregate with facility synchronization and optimistic concurrency control"""

    async def get_by_id(self, conn, plant_id: UUID) -> Optional[Plant]:
        """Get plant by ID with facilities and equipment IDs"""
        # Get plant
        plant_row = await queries.get_by_id(conn, id=plant_id)
        if not plant_row:
            return None

        # Get facilities
        facility_rows = [row async for row in queries.get_facilities(conn, plant_id=plant_id)]
        facilities = []

        for facility_row in facility_rows:
            # Get equipment IDs for this facility
            equipment_rows = [
                row async for row in queries.get_equipment_ids_by_facility(conn, facility_id=facility_row["id"])
            ]
            equipment_ids = [row["id"] for row in equipment_rows]

            facility = Facility(**facility_row, equipment_ids=equipment_ids)
            facilities.append(facility)

        return Plant(**plant_row, facilities=facilities)

    async def get_all(self, conn, modified_since: datetime = DEFAULT_MODIFIED_SINCE) -> PlantListResponse:
        """Get all plants as lightweight list, optionally filtered by modification date"""
        plant_rows = [row async for row in queries.get_all_plants(conn, modified_since=modified_since)]
        plants = [PlantListItem(**row) for row in plant_rows]
        return PlantListResponse(items=plants)

    async def save(self, conn, plant: Plant, force: bool = False) -> Plant:
        """
        Save plant with facility synchronization and optimistic concurrency control.
        Must be called within transaction.

        Args:
            conn: Database connection
            plant_id: Plant ID
            plant: Plant data to save
            force: If True, ignore server_modified_at and mark extra children as deleted

        Raises:
            ConcurrentModificationError: If concurrent modification detected (force=False)
        """
        plant_id = plant.id
        # Get current state if exists
        current = await self.get_by_id(conn, plant_id)

        # New server_modified_at timestamp
        new_server_modified_at = datetime.now(timezone.utc)

        if current and not (force or settings.disable_optimistic_locking):
            OptimisticLockingValidator.validate_object(
                server_obj=current,
                client_obj=plant,
                collection_configs=[
                    CollectionConfig(
                        server_collection=current.facilities,
                        client_collection=plant.facilities,
                        collection_name="facilities",
                    )
                ],
            )

        # Upsert plant (claim fields are managed separately via claim/release endpoints)
        await queries.upsert_plant(
            conn,
            id=plant_id,
            name=plant.name,
            is_deleted=plant.is_deleted,
            server_modified_at=new_server_modified_at,
        )

        # Synchronize facilities
        await self._sync_facilities(conn, plant_id, plant.facilities, force)

        # Return updated aggregate
        result = await self.get_by_id(conn, plant_id)
        if result is None:
            raise ValueError(f"Plant {plant_id} not found after save")
        return result

    async def delete(self, conn, plant_id: UUID) -> bool:
        """Logically delete plant (must be called within transaction)"""
        result = await queries.delete_plant(conn, id=plant_id)
        # asyncpg returns string like "UPDATE 1", psycopg2 returns int (row count)
        if isinstance(result, int):
            return result > 0
        return result is not None and "0" not in result

    async def claim(self, conn, plant_id: UUID, device_id: str, user_id: int) -> Optional[bool]:
        """
        Claim plant for editing (must be called within transaction).
        Updates server_modified_at for sync purposes.

        Returns:
            - True if claim succeeded
            - False if plant is claimed by another user and not stale
            - None if equipment is not found
        """

        # Get current plant state
        current = await self.get_by_id(conn, plant_id)
        if not current:
            return None

        # Check if claiming is allowed
        if current.claimed_by_user_id is not None and current.claimed_by_user_id != user_id:
            # Plant is claimed by another user - check if stale
            if not current.is_stale:
                return False

        # Claim is allowed - update the claim and server_modified_at
        now = datetime.now(timezone.utc)
        result = await queries.claim_plant(
            conn,
            id=plant_id,
            device_id=device_id,
            user_id=user_id,
            claimed_at=now,
            server_modified_at=now,
        )
        # asyncpg returns string like "UPDATE 1", psycopg2 returns int (row count)
        if isinstance(result, int):
            success = result > 0
        else:
            success = result is not None and "0" not in result

        return success

    async def release(self, conn, plant_id: UUID) -> bool:
        """Release plant (must be called within transaction). Updates server_modified_at for sync purposes."""
        result = await queries.release_plant(conn, id=plant_id, server_modified_at=datetime.now(timezone.utc))
        # asyncpg returns string like "UPDATE 1", psycopg2 returns int (row count)
        if isinstance(result, int):
            return result > 0
        return result is not None and "0" not in result

    async def _sync_facilities(self, conn, plant_id: UUID, facilities: list[Facility], force: bool):
        """
        Synchronize facilities: match by ID, add new, mark removed as deleted.

        Args:
            conn: Database connection
            plant_id: Plant ID
            facilities: List of facilities to sync
            force: If True, mark extra facilities as deleted; if False, extras already validated
        """
        # Get existing facility IDs for this plant
        existing_rows = [row async for row in queries.get_facility_ids(conn, plant_id=plant_id)]
        existing_ids = {row["id"] for row in existing_rows}

        incoming_ids = {f.id for f in facilities}

        # Validate that facilities being added/updated don't belong to another plant (never allow stealing)
        for facility in facilities:
            if facility.id not in existing_ids:
                # This is a new facility or existing facility from another plant
                # Check if it exists in another plant
                existing_plant_row = await queries.get_facility_plant_id(conn, facility_id=facility.id)
                if existing_plant_row and existing_plant_row["plant_id"] != plant_id:
                    raise ValueError(
                        f"Cannot transfer facility {facility.id} from another plant "
                        f"({existing_plant_row['plant_id']}). Child entities cannot be stolen."
                    )

        # Update or insert facilities with their is_deleted values
        for facility in facilities:
            await queries.upsert_facility(
                conn,
                id=facility.id,
                plant_id=plant_id,
                name=facility.name,
                facility_template_id=facility.facility_template_id,
                is_deleted=facility.is_deleted,
            )

        # Mark removed facilities as deleted (logical deletion)
        # This happens in both force and non-force modes (non-force already validated no extras)
        to_delete = existing_ids - incoming_ids
        for facility_id in to_delete:
            await queries.mark_facility_deleted(conn, id=facility_id)
