"""Group repository with hierarchical structure and plant membership synchronization"""

import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

import aiosql
from aiosql.queries import Queries

from app.config import settings
from app.constants import DEFAULT_MODIFIED_SINCE
from app.models.plant_group import PlantGroup, PlantGroupListResponse
from app.utils.async_wrapper import AsyncWrapper
from app.utils.db_utils import OptimisticLockingValidator

logger = logging.getLogger(__name__)


# Load queries from single file
_queries = aiosql.from_path("app/queries/plant_group.sql", settings.db_driver)
queries: Queries = AsyncWrapper(_queries) if settings.db_driver == "psycopg2" else _queries  # type: ignore[assignment]


class PlantGroupRepository:
    """Repository for PlantGroup aggregate with plant membership synchronization"""

    async def get_by_id(self, conn, group_id: UUID) -> Optional[PlantGroup]:
        """Get group by ID including its plant_ids"""
        group_row = await queries.get_by_id(conn, id=group_id)
        if not group_row:
            return None

        plant_id_rows = [row async for row in queries.get_plant_ids_by_group(conn, plant_group_id=group_id)]
        plant_ids = [row["plant_id"] for row in plant_id_rows]

        return PlantGroup(
            id=group_row["id"],
            name=group_row["name"],
            parent_id=group_row["parent_id"],
            is_deleted=group_row["is_deleted"],
            server_modified_at=group_row["server_modified_at"],
            plant_ids=plant_ids,
        )

    async def get_all(self, conn, modified_since: datetime = DEFAULT_MODIFIED_SINCE) -> PlantGroupListResponse:
        """Get all groups as list with plant_ids, optionally filtered by modification date.

        Loads all memberships in a single query to avoid N+1.
        """
        group_rows = [row async for row in queries.get_all_groups(conn, modified_since=modified_since)]

        # Load all memberships in one query and group by plant_group_id
        membership_rows = [row async for row in queries.get_all_memberships(conn)]
        memberships: dict[UUID, list[UUID]] = defaultdict(list)
        for row in membership_rows:
            memberships[row["plant_group_id"]].append(row["plant_id"])

        groups = [
            PlantGroup(
                **row,
                plant_ids=memberships.get(row["id"], []),
            )
            for row in group_rows
        ]
        return PlantGroupListResponse(items=groups)

    async def save(self, conn, group: PlantGroup, force: bool = False, move_plants: bool = False) -> PlantGroup:
        """Save group with conflict detection and plant membership synchronization.
        Must be called within a transaction.

        Args:
            conn: Database connection
            group: Group data to save
            force: If True, ignore server_modified_at validation
            move_plants: If True, allow moving plants that already belong to another group.
                         If False (default), raises ValueError if any plant_id in group.plant_ids
                         already belongs to a different group.

        Raises:
            ConcurrentModificationError: If concurrent modification detected (force=False)
            ValueError: If group structure is invalid (self-reference or cyclic dependency)
            ValueError: If a plant already belongs to another group and move_plants=False
        """
        id = group.id
        current = await self.get_by_id(conn, id)

        new_server_modified_at = datetime.now(timezone.utc)

        if current and not (force or settings.disable_optimistic_locking):
            OptimisticLockingValidator.validate_object(
                server_obj=current,
                client_obj=group,
            )

        # Guard: self-reference
        if group.parent_id == id:
            raise ValueError("Group cannot be its own parent")

        # Guard: cycle in tree (only relevant when a parent is set and the group already exists)
        if group.parent_id and current:
            if await self._check_cyclic_dependency(conn, id, group.parent_id):
                raise ValueError("Moving this group would create a cyclic dependency")

        await queries.upsert_group(
            conn,
            id=id,
            name=group.name,
            parent_id=group.parent_id,
            is_deleted=group.is_deleted,
            server_modified_at=new_server_modified_at,
        )

        # Sync plant membership
        await self._sync_plant_ids(conn, id, group.plant_ids, move_plants=move_plants)

        result = await self.get_by_id(conn, id)
        if result is None:
            raise ValueError(f"Group {id} not found after save")

        return result

    async def _sync_plant_ids(self, conn, group_id: UUID, incoming_plant_ids: list[UUID], move_plants: bool) -> None:
        """Synchronize plant membership for a group.

        Args:
            conn: Database connection
            group_id: The group being updated
            incoming_plant_ids: The desired list of plant_ids for this group
            move_plants: If True, plants belonging to another group are moved here.
                         If False, raises ValueError if any plant already belongs to another group.
        """
        # Get current membership for this group
        current_rows = [row async for row in queries.get_plant_ids_by_group(conn, plant_group_id=group_id)]
        current_ids = {row["plant_id"] for row in current_rows}
        incoming_ids = set(incoming_plant_ids)

        to_add = incoming_ids - current_ids
        to_remove = current_ids - incoming_ids

        # Check for plants that belong to a different group
        for plant_id in to_add:
            existing_row = await queries.get_group_id_by_plant(conn, plant_id=plant_id)
            if existing_row is not None:
                existing_group_id = existing_row["plant_group_id"]
                if existing_group_id != group_id:
                    if not move_plants:
                        raise ValueError(
                            f"Plant {plant_id} already belongs to group {existing_group_id}. "
                            "Use move_plants=true to move it to this group."
                        )
                    # move_plants=True: remove from current group first
                    await queries.delete_membership_by_plant(conn, plant_id=plant_id)

        # Remove plants no longer in this group
        for plant_id in to_remove:
            await queries.delete_membership_by_plant(conn, plant_id=plant_id)

        # Add new plants
        for plant_id in to_add:
            await queries.upsert_membership(conn, plant_id=plant_id, plant_group_id=group_id)

    async def _check_cyclic_dependency(self, conn, group_id: UUID, new_parent_id: UUID) -> bool:
        """Check if moving a group to a new parent would create a cyclic dependency.

        Args:
            conn: Database connection
            group_id: UUID of the group being moved
            new_parent_id: UUID of the proposed new parent group

        Returns:
            bool: True if moving would create a cycle, False otherwise
        """
        try:
            result = await queries.check_cyclic_dependency(
                conn,
                id=group_id,
                new_parent_id=new_parent_id,
            )

            if result is None:
                return False
            return bool(result["would_create_cycle"])

        except Exception as e:
            logger.error(f"Error checking cyclic dependency: {e}")
            raise ValueError(f"Failed to check cyclic dependency: {e}")
