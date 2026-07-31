"""Defect repository"""

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

import aiosql
from aiosql.queries import Queries

from app.config import settings
from app.constants import DEFAULT_MODIFIED_SINCE
from app.exceptions import ConcurrentModificationError
from app.models import ConflictDetail, ConflictError
from app.models.defect import Defect, DefectListItem, DefectListResponse
from app.utils.async_wrapper import AsyncWrapper
from app.utils.datetime_utils import truncate_to_milliseconds

# Load queries with configurable driver
_queries = aiosql.from_path("app/queries/defect.sql", settings.db_driver)
queries: Queries = AsyncWrapper(_queries) if settings.db_driver == "psycopg2" else _queries  # type: ignore[assignment]


class DefectRepository:
    """Repository for Defect aggregate with optimistic concurrency control"""

    async def get_by_id(self, conn, defect_id: UUID) -> Optional[Defect]:
        """Get defect by ID"""
        defect_row = await queries.get_by_id(conn, id=defect_id)
        if not defect_row:
            return None
        return Defect(**defect_row)

    async def get_all(self, conn, modified_since: datetime = DEFAULT_MODIFIED_SINCE) -> DefectListResponse:
        """Get all defects as lightweight list, optionally filtered by modification date"""
        defect_rows = [row async for row in queries.get_all_defects(conn, modified_since=modified_since)]
        defect_list = [DefectListItem(**row) for row in defect_rows]
        return DefectListResponse(items=defect_list)

    async def get_by_plant_id(
        self, conn, plant_id: UUID, modified_since: datetime = DEFAULT_MODIFIED_SINCE
    ) -> list[Defect]:
        """Get all defects for a plant (full data)"""
        defect_rows = [
            row async for row in queries.get_by_plant_id(conn, plant_id=plant_id, modified_since=modified_since)
        ]
        return [Defect(**row) for row in defect_rows]

    async def save(self, conn, defect: Defect, force: bool = False) -> Defect:
        """
        Save defect with optimistic concurrency control.
        Must be called within transaction.

        Args:
            conn: Database connection
            defect: Defect data to save
            force: If True, ignore server_modified_at validation

        Raises:
            ConcurrentModificationError: If concurrent modification detected (force=False)
        """
        defect_id = defect.id

        # Get current state if exists
        current = await self.get_by_id(conn, defect_id)

        # New server_modified_at timestamp
        new_server_modified_at = datetime.now(timezone.utc)

        if current and not (force or settings.disable_optimistic_locking):
            # Validate server_modified_at for existing defect
            assert current.server_modified_at is not None
            if defect.server_modified_at is None:
                raise ConcurrentModificationError(
                    ConflictError(
                        message="server_modified_at is required for updating existing defect",
                        server_modified_at=current.server_modified_at,
                        conflicts=[
                            ConflictDetail(
                                field="server_modified_at",
                                message="Missing server_modified_at in request",
                            )
                        ],
                    )
                )

            if truncate_to_milliseconds(defect.server_modified_at) != truncate_to_milliseconds(
                current.server_modified_at
            ):
                raise ConcurrentModificationError(
                    ConflictError(
                        message="Defect was modified by another client",
                        server_modified_at=current.server_modified_at,
                        client_modified_at=defect.server_modified_at,
                        conflicts=[
                            ConflictDetail(
                                field="server_modified_at",
                                message="Timestamp mismatch",
                                server_value=current.server_modified_at.isoformat(),
                                client_value=defect.server_modified_at.isoformat(),
                            )
                        ],
                    )
                )

        # Upsert defect
        await queries.upsert_defect(
            conn,
            id=defect_id,
            equipment_id=defect.equipment_id,
            unit_name=defect.unit_name,
            defect_type_id=defect.defect_type_id,
            detected_at=defect.detected_at,
            resolved_at=defect.resolved_at,
            status=defect.status.value,
            is_deleted=defect.is_deleted,
            server_modified_at=new_server_modified_at,
        )

        # Return updated defect
        result = await self.get_by_id(conn, defect_id)
        if result is None:
            raise ValueError(f"Defect {defect_id} not found after save")
        return result

    async def delete(self, conn, defect_id: UUID) -> bool:
        """Logically delete defect (must be called within transaction)"""
        result = await queries.delete_defect(conn, id=defect_id)
        return result is not None and "0" not in result
