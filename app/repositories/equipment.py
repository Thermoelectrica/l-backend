"""Equipment repository"""

from datetime import datetime, timezone
from typing import Optional, Sequence
from uuid import UUID

import aiosql
from aiosql.queries import Queries

from app.config import settings
from app.constants import DEFAULT_MODIFIED_SINCE
from app.exceptions import ConcurrentModificationError
from app.models import ConflictDetail, ConflictError
from app.models.equipment import (
    ControlPoint,
    Equipment,
    EquipmentListItem,
    EquipmentListResponse,
)
from app.utils.async_wrapper import AsyncWrapper
from app.utils.datetime_utils import truncate_to_milliseconds

# Load queries with configurable driver
_queries = aiosql.from_path("app/queries/equipment.sql", settings.db_driver)
queries: Queries = AsyncWrapper(_queries) if settings.db_driver == "psycopg2" else _queries  # type: ignore[assignment]


class EquipmentRepository:
    """Repository for Equipment aggregate with control point and defect synchronization
    and optimistic concurrency control"""

    def _build_equipment_aggregates(
        self,
        equipment_rows: list,
        control_point_rows: list,
        defect_rows: list,
        inspection_rows: list,
    ) -> list[Equipment]:
        """
        Build Equipment aggregates from separate row lists.

        Args:
            equipment_rows: List of equipment rows
            control_point_rows: List of control point rows (must have equipment_id)
            defect_rows: List of defect rows (must have equipment_id) - IGNORED for backwards compatibility
            inspection_rows: List of inspection rows (must have equipment_id)

        Returns:
            List of Equipment instances
        """
        # Group control points by equipment_id
        control_points_by_equipment = {}
        for row in control_point_rows:
            equipment_id = row["equipment_id"]
            if equipment_id not in control_points_by_equipment:
                control_points_by_equipment[equipment_id] = []
            control_points_by_equipment[equipment_id].append(
                ControlPoint(**{k: v for k, v in row.items() if k != "equipment_id"})
            )

        # DEPRECATED: Defects are now managed via separate defect router
        # Always return empty list for backwards compatibility
        # defect_rows parameter is ignored

        # Group inspection IDs by equipment_id
        inspections_by_equipment = {}
        for row in inspection_rows:
            equipment_id = row["equipment_id"]
            if equipment_id not in inspections_by_equipment:
                inspections_by_equipment[equipment_id] = []
            inspections_by_equipment[equipment_id].append(row["id"])

        # Build Equipment instances
        equipment_list = []
        for equipment_row in equipment_rows:
            equipment_id = equipment_row["id"]
            equipment = Equipment(
                **equipment_row,
                control_points=control_points_by_equipment.get(equipment_id, []),
                defects=[],  # Always empty for backwards compatibility
                inspection_ids=inspections_by_equipment.get(equipment_id, []),
            )
            equipment_list.append(equipment)

        return equipment_list

    async def get_by_id(self, conn, equipment_id: UUID) -> Optional[Equipment]:
        """Get equipment by ID with control points and inspection IDs (defects always empty)"""
        # Get equipment
        equipment_row = await queries.get_by_id(conn, id=equipment_id)
        if not equipment_row:
            return None

        # Get control points
        control_point_rows = [row async for row in queries.get_control_points(conn, equipment_id=equipment_id)]

        # DEPRECATED: Defects are now managed via separate defect router
        # Always return empty list for backwards compatibility
        defect_rows = []

        # Get inspection IDs
        inspection_rows = [row async for row in queries.get_inspection_ids(conn, equipment_id=equipment_id)]

        # Build and return single equipment aggregate
        equipment_list = self._build_equipment_aggregates(
            [equipment_row], control_point_rows, defect_rows, inspection_rows
        )

        return equipment_list[0] if equipment_list else None

    async def get_all(self, conn, modified_since: datetime = DEFAULT_MODIFIED_SINCE) -> EquipmentListResponse:
        """Get all equipment as lightweight list, optionally filtered by modification date"""
        equipment_rows = [row async for row in queries.get_all_equipment(conn, modified_since=modified_since)]
        equipment_list = [EquipmentListItem(**row) for row in equipment_rows]
        return EquipmentListResponse(items=equipment_list)

    async def get_by_plant_id(
        self, conn, plant_id: UUID, modified_since: datetime = DEFAULT_MODIFIED_SINCE
    ) -> list[Equipment]:
        """Get all equipment for a plant (full aggregates, defects always empty) - uses batch queries for efficiency"""
        # Fetch all data in parallel using batch queries
        equipment_rows = [
            row async for row in queries.get_by_plant_id(conn, plant_id=plant_id, modified_since=modified_since)
        ]

        if not equipment_rows:
            return []

        # Fetch all related data for the plant in batch
        control_point_rows = [row async for row in queries.get_control_points_by_plant(conn, plant_id=plant_id)]
        # DEPRECATED: Defects are now managed via separate defect router
        # Always return empty list for backwards compatibility
        defect_rows = []

        inspection_rows = [row async for row in queries.get_inspections_by_plant(conn, plant_id=plant_id)]

        # Build and return equipment aggregates
        return self._build_equipment_aggregates(equipment_rows, control_point_rows, defect_rows, inspection_rows)

    async def save(self, conn, equipment: Equipment, force: bool = False) -> Equipment:
        """
        Save equipment with control point and defect synchronization and optimistic concurrency control.
        Must be called within transaction.

        Args:
            conn: Database connection
            equipment_id: Equipment ID
            equipment: Equipment data to save
            force: If True, ignore server_modified_at and mark extra children as deleted

        Raises:
            ConcurrentModificationError: If concurrent modification detected (force=False)
        """
        equipment_id = equipment.id

        # Get current state if exists
        current = await self.get_by_id(conn, equipment_id)

        # New server_modified_at timestamp
        new_server_modified_at = datetime.now(timezone.utc)

        if current and not (force or settings.disable_optimistic_locking):
            # Validate server_modified_at for existing equipment
            if equipment.server_modified_at is None:
                raise ConcurrentModificationError(
                    ConflictError(
                        message="server_modified_at is required for updating existing equipment",
                        server_modified_at=current.server_modified_at,
                        conflicts=[
                            ConflictDetail(
                                field="server_modified_at",
                                message="Missing server_modified_at in request",
                            )
                        ],
                    )
                )

            if truncate_to_milliseconds(equipment.server_modified_at) != truncate_to_milliseconds(
                current.server_modified_at
            ):
                raise ConcurrentModificationError(
                    ConflictError(
                        message="Equipment was modified by another client",
                        server_modified_at=current.server_modified_at,
                        client_modified_at=equipment.server_modified_at,
                        conflicts=[
                            ConflictDetail(
                                field="server_modified_at",
                                message="Timestamp mismatch",
                                server_value=current.server_modified_at.isoformat(),
                                client_value=equipment.server_modified_at.isoformat(),
                            )
                        ],
                    )
                )

            # Check for extra control points on server
            current_cp_ids = {cp.id for cp in current.control_points if not cp.is_deleted}
            incoming_cp_ids = {cp.id for cp in equipment.control_points}
            extra_cp_ids = current_cp_ids - incoming_cp_ids

            # DEPRECATED: Defects are now managed via separate defect router
            # Ignore defects in validation for backwards compatibility

            if extra_cp_ids:
                raise ConcurrentModificationError(
                    ConflictError(
                        message="Extra child entities exist on server",
                        server_modified_at=current.server_modified_at,
                        client_modified_at=equipment.server_modified_at,
                        extra_child_ids=list(extra_cp_ids),
                        conflicts=[
                            ConflictDetail(
                                field="control_points",
                                message=f"Server has {len(extra_cp_ids)} extra control points not in client request",
                            )
                        ],
                    )
                )

        # Upsert equipment
        await queries.upsert_equipment(
            conn,
            id=equipment_id,
            facility_id=equipment.facility_id,
            parent_id=equipment.parent_id,
            name=equipment.name,
            qr_code=equipment.qr_code,
            is_container=equipment.is_container,
            equipment_type_id=equipment.equipment_type_id,
            facility_template_equipment_id=equipment.facility_template_equipment_id,
            estimated_point_count=equipment.estimated_point_count,
            is_deleted=equipment.is_deleted,
            server_modified_at=new_server_modified_at,
        )

        # Synchronize control points
        await self._sync_control_points(conn, equipment_id, equipment.control_points, force)

        # DEPRECATED: Defects are now managed via separate defect router
        # Ignore defects in save for backwards compatibility
        # await self._sync_defects(conn, equipment_id, equipment.defects, force)

        # Return updated aggregate
        result = await self.get_by_id(conn, equipment_id)
        if result is None:
            raise ValueError(f"Equipment {equipment_id} not found after save")
        return result

    async def delete(self, conn, equipment_id: UUID) -> bool:
        """Logically delete equipment (must be called within transaction)"""
        result = await queries.delete_equipment(conn, id=equipment_id)
        return result is not None and "0" not in result

    async def _sync_control_points(
        self,
        conn,
        equipment_id: UUID,
        control_points: Sequence[ControlPoint],
        force: bool,
    ):
        """
        Synchronize control points: match by ID, add new, mark removed as deleted.

        Args:
            conn: Database connection
            equipment_id: Equipment ID
            control_points: List of control points to sync
            force: If True, mark extra control points as deleted; if False, extras already validated
        """
        # Get existing control point IDs for this equipment
        existing_rows = [row async for row in queries.get_control_point_ids(conn, equipment_id=equipment_id)]
        existing_ids = {row["id"] for row in existing_rows}

        incoming_ids = {cp.id for cp in control_points}

        # Validate that control points being added/updated don't belong to another equipment (never allow stealing)
        for control_point in control_points:
            if control_point.id not in existing_ids:
                # This is a new control point or existing control point from another equipment
                # Check if it exists in another equipment
                existing_equipment_row = await queries.get_control_point_equipment_id(
                    conn, control_point_id=control_point.id
                )
                if existing_equipment_row and existing_equipment_row["equipment_id"] != equipment_id:
                    raise ValueError(
                        f"Cannot transfer control point {control_point.id} from another equipment "
                        f"({existing_equipment_row['equipment_id']}). Child entities cannot be stolen."
                    )

        # Update or insert
        for control_point in control_points:
            await queries.upsert_control_point(
                conn,
                id=control_point.id,
                equipment_id=equipment_id,
                control_point_type=control_point.control_point_type,
                point_count=control_point.point_count,
                sticker_count=control_point.sticker_count,
                sticker_type_id=control_point.sticker_type_id,
                is_deleted=control_point.is_deleted,
            )

        if force:
            # Mark removed control points as deleted (logical deletion)
            to_delete = existing_ids - incoming_ids
            for cp_id in to_delete:
                await queries.mark_control_point_deleted(conn, id=cp_id)

    # DEPRECATED: _sync_defects method removed
    # Defects are now managed via separate defect router
    # This method is no longer called from save()
