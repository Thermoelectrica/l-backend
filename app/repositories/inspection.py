"""Inspection repository"""

from datetime import datetime, timezone
from typing import Optional, Sequence
from uuid import UUID

import aiosql
from aiosql.queries import Queries

from app.config import settings
from app.constants import DEFAULT_MODIFIED_SINCE
from app.exceptions import ConcurrentModificationError
from app.models import ConflictDetail, ConflictError
from app.models.inspection import (
    ImageLink,
    Inspection,
    InspectionListItem,
    InspectionListResponse,
    InspectionStep,
)
from app.utils.async_wrapper import AsyncWrapper
from app.utils.datetime_utils import truncate_to_milliseconds

# Load queries with configurable driver
_queries = aiosql.from_path("app/queries/inspection.sql", settings.db_driver)
queries: Queries = AsyncWrapper(_queries) if settings.db_driver == "psycopg2" else _queries  # type: ignore[assignment]


class InspectionRepository:
    """Repository for Inspection aggregate with step and image link synchronization
    and optimistic concurrency control"""

    def _build_inspection_aggregates(
        self, inspection_rows: list, step_rows: list, image_link_rows: list
    ) -> list[Inspection]:
        """
        Build Inspection aggregates from separate row lists.

        Args:
            inspection_rows: List of inspection rows
            step_rows: List of step rows (must have inspection_id)
            image_link_rows: List of image link rows (must have inspection_step_id)

        Returns:
            List of Inspection instances
        """
        # Group image links by inspection_step_id
        image_links_by_step = {}
        for row in image_link_rows:
            step_id = row["inspection_step_id"]
            if step_id not in image_links_by_step:
                image_links_by_step[step_id] = []
            image_links_by_step[step_id].append(
                ImageLink(image_id=row["image_id"], is_deleted=row.get("is_deleted", False))
            )

        # Group steps by inspection_id
        steps_by_inspection = {}
        for row in step_rows:
            inspection_id = row["inspection_id"]
            if inspection_id not in steps_by_inspection:
                steps_by_inspection[inspection_id] = []

            step_data = {k: v for k, v in row.items() if k != "inspection_id"}
            step_id = step_data["id"]
            step = InspectionStep(**step_data, image_links=image_links_by_step.get(step_id, []))
            steps_by_inspection[inspection_id].append(step)

        # Build Inspection instances
        inspection_list = []
        for inspection_row in inspection_rows:
            inspection_id = inspection_row["id"]
            inspection = Inspection(**inspection_row, steps=steps_by_inspection.get(inspection_id, []))
            inspection_list.append(inspection)

        return inspection_list

    async def get_by_id(self, conn, inspection_id: UUID) -> Optional[Inspection]:
        """Get inspection by ID with steps and image links"""
        # Get inspection
        inspection_row = await queries.get_by_id(conn, id=inspection_id)
        if not inspection_row:
            return None

        # Get steps
        step_rows = [row async for row in queries.get_steps(conn, inspection_id=inspection_id)]

        # Get image links for all steps
        image_link_rows = []
        for step_row in step_rows:
            links = [row async for row in queries.get_image_links(conn, inspection_step_id=step_row["id"])]
            for link in links:
                image_link_rows.append(
                    {
                        "image_id": link["image_id"],
                        "inspection_step_id": step_row["id"],
                        "is_deleted": link.get("is_deleted", False),
                    }
                )

        # Build and return single inspection aggregate
        inspection_list = self._build_inspection_aggregates([inspection_row], step_rows, image_link_rows)

        return inspection_list[0] if inspection_list else None

    async def get_all(self, conn, modified_since: datetime = DEFAULT_MODIFIED_SINCE) -> InspectionListResponse:
        """Get all inspections as lightweight list, optionally filtered by modification date"""
        inspection_rows = [row async for row in queries.get_all_inspections(conn, modified_since=modified_since)]
        inspection_list = [InspectionListItem(**row) for row in inspection_rows]
        return InspectionListResponse(items=inspection_list)

    async def get_by_plant_id(
        self, conn, plant_id: UUID, modified_since: datetime = DEFAULT_MODIFIED_SINCE
    ) -> list[Inspection]:
        """Get all inspections for plant (full aggregates) - uses batch queries for efficiency"""
        # Fetch all data in parallel using batch queries
        inspection_rows = [
            row async for row in queries.get_by_plant_id(conn, plant_id=plant_id, modified_since=modified_since)
        ]

        if not inspection_rows:
            return []

        # Fetch all related data for the plant in batch
        step_rows = [row async for row in queries.get_steps_by_plant(conn, plant_id=plant_id)]
        image_link_rows = [row async for row in queries.get_image_links_by_plant(conn, plant_id=plant_id)]

        # Build and return inspection aggregates
        return self._build_inspection_aggregates(inspection_rows, step_rows, image_link_rows)

    async def save(self, conn, inspection: Inspection, force: bool = False) -> Inspection:
        """
        Save inspection with step and image link synchronization and optimistic concurrency control.
        Must be called within transaction.

        Args:
            conn: Database connection
            inspection: Inspection data to save
            force: If True, ignore server_modified_at and mark extra children as deleted

        Raises:
            ConcurrentModificationError: If concurrent modification detected (force=False)
        """
        inspection_id = inspection.id

        # Get current state if exists
        current = await self.get_by_id(conn, inspection_id)

        # New server_modified_at timestamp
        new_server_modified_at = datetime.now(timezone.utc)

        if current and not (force or settings.disable_optimistic_locking):
            # Validate server_modified_at for existing inspection
            if inspection.server_modified_at is None:
                raise ConcurrentModificationError(
                    ConflictError(
                        message="server_modified_at is required for updating existing inspection",
                        server_modified_at=current.server_modified_at,
                        conflicts=[
                            ConflictDetail(
                                field="server_modified_at",
                                message="Missing server_modified_at in request",
                            )
                        ],
                    )
                )

            if truncate_to_milliseconds(inspection.server_modified_at) != truncate_to_milliseconds(
                current.server_modified_at
            ):
                raise ConcurrentModificationError(
                    ConflictError(
                        message="Inspection was modified by another client",
                        server_modified_at=current.server_modified_at,
                        client_modified_at=inspection.server_modified_at,
                        conflicts=[
                            ConflictDetail(
                                field="server_modified_at",
                                message="Timestamp mismatch",
                                server_value=current.server_modified_at.isoformat(),
                                client_value=inspection.server_modified_at.isoformat(),
                            )
                        ],
                    )
                )

            # Check for extra steps on server
            current_step_ids = {step.id for step in current.steps if not step.is_deleted}
            incoming_step_ids = {step.id for step in inspection.steps}
            extra_step_ids = current_step_ids - incoming_step_ids

            if extra_step_ids:
                raise ConcurrentModificationError(
                    ConflictError(
                        message="Extra child entities exist on server",
                        server_modified_at=current.server_modified_at,
                        client_modified_at=inspection.server_modified_at,
                        extra_child_ids=list(extra_step_ids),
                        conflicts=[
                            ConflictDetail(
                                field="steps",
                                message=f"Server has {len(extra_step_ids)} extra steps not in client request",
                            )
                        ],
                    )
                )

        # Upsert inspection
        await queries.upsert_inspection(
            conn,
            id=inspection_id,
            equipment_id=inspection.equipment_id,
            inspector_id=inspection.inspector_id,
            started_at=inspection.started_at,
            completed_at=inspection.completed_at,
            status=inspection.status.value,
            is_deleted=inspection.is_deleted,
            server_modified_at=new_server_modified_at,
        )

        # Synchronize steps
        await self._sync_steps(conn, inspection_id, inspection.steps, force)

        # Return updated aggregate
        result = await self.get_by_id(conn, inspection_id)
        if result is None:
            raise ValueError(f"Inspection {inspection_id} not found after save")
        return result

    async def delete(self, conn, inspection_id: UUID) -> bool:
        """Logically delete inspection (must be called within transaction)"""
        result = await queries.delete_inspection(conn, id=inspection_id)
        return result is not None and "0" not in result

    async def _sync_steps(self, conn, inspection_id: UUID, steps: Sequence[InspectionStep], force: bool):
        """
        Synchronize steps: match by ID, add new, mark removed as deleted.

        Args:
            conn: Database connection
            inspection_id: Inspection ID
            steps: List of steps to sync
            force: If True, mark extra steps as deleted; if False, extras already validated
        """
        # Get existing step IDs for this inspection
        existing_rows = [row async for row in queries.get_step_ids(conn, inspection_id=inspection_id)]
        existing_ids = {row["id"] for row in existing_rows}

        incoming_ids = {step.id for step in steps}

        # Validate that steps being added/updated don't belong to another inspection (never allow stealing)
        for step in steps:
            if step.id not in existing_ids:
                # This is a new step or existing step from another inspection
                # Check if it exists in another inspection
                existing_inspection_row = await queries.get_step_inspection_id(conn, step_id=step.id)
                if existing_inspection_row and existing_inspection_row["inspection_id"] != inspection_id:
                    raise ValueError(
                        f"Cannot transfer step {step.id} from another inspection "
                        f"({existing_inspection_row['inspection_id']}). Child entities cannot be stolen."
                    )

        # Update or insert steps
        for step in steps:
            await queries.upsert_step(
                conn,
                id=step.id,
                started_at=step.started_at,
                inspection_id=inspection_id,
                step_number=step.step_number,
                step_type=step.step_type.value,
                defect_id=step.defect_id,
                unit_name=step.unit_name,
                description=step.description,
                is_resolved=step.is_resolved,
                sticker_type_id=step.sticker_type_id,
                t_sticker=step.t_sticker,
                t_environment=step.t_environment,
                t_similar_unit=step.t_similar_unit,
                epsilon=step.epsilon,
                t_observed=step.t_observed,
                measured_current=step.measured_current,
                nominal_current=step.nominal_current,
                defect_type_id=step.defect_type_id,
                is_sticker_present=step.is_sticker_present,
                is_test_ready=step.is_test_ready,
                is_attention_required=step.is_attention_required,
                step_status=step.step_status.value if step.step_status else None,
                is_deleted=step.is_deleted,
            )

            # Synchronize image links for this step
            await self._sync_image_links(conn, step.id, step.image_links)

        if force:
            # Mark removed steps as deleted (logical deletion)
            to_delete = existing_ids - incoming_ids
            for step_id in to_delete:
                await queries.mark_step_deleted(conn, id=step_id)

    async def _sync_image_links(self, conn, inspection_step_id: UUID, image_links: Sequence[ImageLink]):
        """
        Synchronize image links: match by image_id, upsert all, mark removed as deleted.

        Args:
            conn: Database connection
            inspection_step_id: Inspection step ID
            image_links: List of image links to sync
        """
        # Get existing image link IDs for this step
        existing_rows = [row async for row in queries.get_image_link_ids(conn, inspection_step_id=inspection_step_id)]
        existing_ids = {row["image_id"] for row in existing_rows}

        incoming_ids = {link.image_id for link in image_links}

        # Upsert all image links (add new or update existing)
        for link in image_links:
            await queries.upsert_image_link(
                conn,
                image_id=link.image_id,
                inspection_step_id=inspection_step_id,
                is_deleted=link.is_deleted,
            )

        # Mark removed image links as deleted (logical deletion)
        to_delete = existing_ids - incoming_ids
        for image_id in to_delete:
            await queries.mark_image_link_deleted(conn, image_id=image_id, inspection_step_id=inspection_step_id)
