"""IESK inspection repository"""

from datetime import datetime, timezone
from typing import Optional, Sequence
from uuid import UUID

import aiosql
from aiosql.queries import Queries

from app.config import settings
from app.constants import DEFAULT_MODIFIED_SINCE
from app.models.iesk_inspection import (
    IeskImageLink,
    IeskInspection,
    IeskInspectionListItem,
)
from app.utils.async_wrapper import AsyncWrapper
from app.utils.db_utils import OptimisticLockingValidator

# Load queries with configurable driver
_queries = aiosql.from_path("app/queries/iesk_inspection.sql", settings.db_driver)
queries: Queries = AsyncWrapper(_queries) if settings.db_driver == "psycopg2" else _queries  # type: ignore[assignment]


class IeskInspectionRepository:
    """Repository for IeskInspection aggregate with image link synchronization
    and optimistic concurrency control"""

    def _build_aggregates(self, inspection_rows: list, image_link_rows: list) -> list[IeskInspection]:
        """
        Build IeskInspection aggregates from separate row lists.

        Args:
            inspection_rows: List of iesk_inspection rows
            image_link_rows: List of image link rows (must have iesk_inspection_id)
        """
        links_by_inspection: dict[UUID, list[IeskImageLink]] = {}
        for row in image_link_rows:
            links_by_inspection.setdefault(row["iesk_inspection_id"], []).append(
                IeskImageLink(image_id=row["image_id"], is_deleted=row["is_deleted"])
            )

        return [
            IeskInspection(**dict(row), image_links=links_by_inspection.get(row["id"], [])) for row in inspection_rows
        ]

    async def get_by_id(self, conn, inspection_id: UUID) -> Optional[IeskInspection]:
        """Get IESK inspection by ID with image links (including logically deleted ones)"""
        inspection_row = await queries.get_by_id(conn, id=inspection_id)
        if not inspection_row:
            return None

        link_rows = [
            {"iesk_inspection_id": inspection_id, "image_id": row["image_id"], "is_deleted": row["is_deleted"]}
            async for row in queries.get_iesk_image_links(conn, iesk_inspection_id=inspection_id)
        ]
        return self._build_aggregates([inspection_row], link_rows)[0]

    async def get_all(
        self, conn, modified_since: datetime = DEFAULT_MODIFIED_SINCE
    ) -> list[tuple[UUID, IeskInspectionListItem]]:
        """
        Get all IESK inspections as lightweight items, optionally filtered by modification date.

        Returns:
            (plant_id, item) pairs, so the caller can filter by accessible plants without extra queries
        """
        rows = [row async for row in queries.get_all_iesk_inspections(conn, modified_since=modified_since)]
        return [
            (row["plant_id"], IeskInspectionListItem(**{k: v for k, v in dict(row).items() if k != "plant_id"}))
            for row in rows
        ]

    async def get_by_plant_id(
        self, conn, plant_id: UUID, modified_since: datetime = DEFAULT_MODIFIED_SINCE
    ) -> list[IeskInspection]:
        """Get all IESK inspections for plant (full aggregates) - uses batch queries for efficiency"""
        inspection_rows = [
            row
            async for row in queries.get_iesk_inspections_by_plant_id(
                conn, plant_id=plant_id, modified_since=modified_since
            )
        ]
        if not inspection_rows:
            return []

        link_rows = [
            row
            async for row in queries.get_iesk_image_links_by_plant(
                conn, plant_id=plant_id, modified_since=modified_since
            )
        ]
        return self._build_aggregates(inspection_rows, link_rows)

    async def save(self, conn, inspection: IeskInspection, force: bool = False) -> IeskInspection:
        """
        Save IESK inspection with image link synchronization and optimistic concurrency control.
        Must be called within transaction.

        Args:
            conn: Database connection
            inspection: IESK inspection data to save
            force: If True, ignore server_modified_at

        Raises:
            ConcurrentModificationError: If concurrent modification detected (force=False)
        """
        inspection_id = inspection.id
        current = await self.get_by_id(conn, inspection_id)

        if current and not (force or settings.disable_optimistic_locking):
            # Image links are not checked for "extra children": like inspection_image_link they are
            # always synchronized (missing ones are marked deleted). Any change to them moves the root
            # server_modified_at, so a client with the current timestamp has seen all links.
            OptimisticLockingValidator.validate_object(server_obj=current, client_obj=inspection)

        await queries.upsert_iesk_inspection(
            conn,
            id=inspection_id,
            equipment_id=inspection.equipment_id,
            inspector_id=inspection.inspector_id,
            created_at=inspection.created_at,
            oil_level=inspection.oil_level,
            bugs=inspection.bugs,
            dimensions=inspection.dimensions,
            locks=inspection.locks,
            stickers=inspection.stickers,
            comment=inspection.comment,
            is_deleted=inspection.is_deleted,
            server_modified_at=datetime.now(timezone.utc),
        )

        await self._sync_image_links(conn, inspection_id, inspection.image_links)

        result = await self.get_by_id(conn, inspection_id)
        if result is None:
            raise ValueError(f"IESK inspection {inspection_id} not found after save")
        return result

    async def delete(self, conn, inspection_id: UUID) -> bool:
        """Logically delete IESK inspection (must be called within transaction)"""
        result = await queries.delete_iesk_inspection(conn, id=inspection_id)
        # asyncpg returns string like "UPDATE 1", psycopg2 returns int (row count)
        if isinstance(result, int):
            return result > 0
        return result is not None and "0" not in result

    async def _sync_image_links(self, conn, inspection_id: UUID, image_links: Sequence[IeskImageLink]):
        """
        Synchronize image links: upsert all incoming, mark missing ones as deleted.
        Same rules as InspectionRepository._sync_image_links.
        """
        existing_ids = {
            row["image_id"] async for row in queries.get_iesk_image_links(conn, iesk_inspection_id=inspection_id)
        }
        incoming_ids = {link.image_id for link in image_links}

        for link in image_links:
            await queries.upsert_iesk_image_link(
                conn,
                iesk_inspection_id=inspection_id,
                image_id=link.image_id,
                is_deleted=link.is_deleted,
            )

        for image_id in existing_ids - incoming_ids:
            await queries.mark_iesk_image_link_deleted(conn, iesk_inspection_id=inspection_id, image_id=image_id)
