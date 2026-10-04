"""Verification repository"""

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

import aiosql
from aiosql.queries import Queries

from app.config import settings
from app.constants import DEFAULT_MODIFIED_SINCE
from app.exceptions import ConcurrentModificationError
from app.models import ConflictDetail, ConflictError
from app.models.verification import (
    Verification,
    VerificationEvent,
    VerificationEventType,
    VerificationImageLink,
    VerificationListResponse,
    VerificationStatus,
)
from app.utils.async_wrapper import AsyncWrapper
from app.utils.datetime_utils import truncate_to_milliseconds

# Load queries with configurable driver
_queries = aiosql.from_path("app/queries/verification.sql", settings.db_driver)
queries: Queries = AsyncWrapper(_queries) if settings.db_driver == "psycopg2" else _queries  # type: ignore[assignment]


class VerificationRepository:
    """Repository for Verification aggregate with optimistic concurrency control"""

    def _build_verification_aggregate(
        self, verification_row: dict, image_link_rows: list, event_rows: list
    ) -> Verification:
        """
        Build Verification aggregate from separate row lists.

        Args:
            verification_row: Single verification row
            image_link_rows: List of image link rows
            event_rows: List of event rows

        Returns:
            Verification instance
        """
        image_links = [
            VerificationImageLink(image_id=row["image_id"], is_deleted=row.get("is_deleted", False))
            for row in image_link_rows
        ]

        events = [
            VerificationEvent(
                id=row["id"],
                verification_id=row["verification_id"],
                event_type=VerificationEventType(row["event_type"]),
                inspector_id=row["inspector_id"],
                comment=row.get("comment"),
                created_at=row["created_at"],
            )
            for row in event_rows
        ]

        return Verification(
            **{k: v for k, v in verification_row.items() if k not in ("image_links", "events")},
            image_links=image_links,
            events=events,
        )

    async def get_by_id(self, conn, verification_id: UUID) -> Optional[Verification]:
        """Get verification by ID with image links and events"""
        verification_row = await queries.get_verification_by_id(conn, id=verification_id)
        if not verification_row:
            return None

        image_link_rows = [
            row async for row in queries.get_verification_image_links(conn, verification_id=verification_id)
        ]
        event_rows = [row async for row in queries.get_verification_events(conn, verification_id=verification_id)]

        return self._build_verification_aggregate(verification_row, image_link_rows, event_rows)

    async def get_by_inspector(
        self, conn, inspector_id: int, modified_since: datetime = DEFAULT_MODIFIED_SINCE
    ) -> VerificationListResponse:
        """Get all verifications submitted by inspector, optionally filtered by modification date"""
        verification_rows = [
            row
            async for row in queries.get_verifications_by_inspector(
                conn, inspector_id=inspector_id, modified_since=modified_since
            )
        ]

        verifications = []
        for verification_row in verification_rows:
            image_link_rows = [
                row async for row in queries.get_verification_image_links(conn, verification_id=verification_row["id"])
            ]
            event_rows = [
                row async for row in queries.get_verification_events(conn, verification_id=verification_row["id"])
            ]
            verifications.append(self._build_verification_aggregate(verification_row, image_link_rows, event_rows))

        return VerificationListResponse(items=verifications)

    async def get_by_verifier(
        self, conn, verifier_id: int, modified_since: datetime = DEFAULT_MODIFIED_SINCE
    ) -> VerificationListResponse:
        """Get all verifications assigned to verifier, optionally filtered by modification date"""
        verification_rows = [
            row
            async for row in queries.get_verifications_by_verifier(
                conn, verifier_id=verifier_id, modified_since=modified_since
            )
        ]

        verifications = []
        for verification_row in verification_rows:
            image_link_rows = [
                row async for row in queries.get_verification_image_links(conn, verification_id=verification_row["id"])
            ]
            event_rows = [
                row async for row in queries.get_verification_events(conn, verification_id=verification_row["id"])
            ]
            verifications.append(self._build_verification_aggregate(verification_row, image_link_rows, event_rows))

        return VerificationListResponse(items=verifications)

    async def get_active_verification_by_step(self, conn, inspection_step_id: UUID) -> Optional[dict]:
        """Check if active (non-APPROVED, non-deleted) verification exists for step"""
        return await queries.get_active_verification_by_step(conn, inspection_step_id=inspection_step_id)

    async def get_inspection_step_data(self, conn, step_id: UUID) -> Optional[dict]:
        """Get inspection step data with plant_id for copying to verification"""
        return await queries.get_inspection_step_data(conn, step_id=step_id)

    async def get_inspection_step_image_links(self, conn, step_id: UUID) -> list:
        """Get image links for inspection step (to copy to verification)"""
        return [row async for row in queries.get_inspection_step_image_links(conn, step_id=step_id)]

    async def get_inspector_info(self, conn, inspector_id: int) -> Optional[dict]:
        """Get inspector access level and is_deleted for validation"""
        return await queries.get_inspector_access_level(conn, inspector_id=inspector_id)

    async def create(
        self,
        conn,
        verification: Verification,
        image_links: list[VerificationImageLink],
    ) -> Verification:
        """
        Create new verification with initial image links and SUBMITTED event.
        Must be called within transaction.

        Args:
            conn: Database connection
            verification: Verification data
            image_links: Initial image links to associate

        Returns:
            Created verification with image links and events
        """
        verification_id = verification.id
        server_modified_at = datetime.now(timezone.utc)

        # Insert verification
        await queries.insert_verification(
            conn,
            id=verification_id,
            inspection_step_id=verification.inspection_step_id,
            plant_id=verification.plant_id,
            inspector_id=verification.inspector_id,
            verifier_id=verification.verifier_id,
            status=verification.status.value,
            server_modified_at=server_modified_at,
            step_type=verification.step_type,
            defect_id=verification.defect_id,
            unit_name=verification.unit_name,
            description=verification.description,
            is_resolved=verification.is_resolved,
            sticker_type_id=verification.sticker_type_id,
            t_sticker=verification.t_sticker,
            t_environment=verification.t_environment,
            t_similar_unit=verification.t_similar_unit,
            epsilon=verification.epsilon,
            t_observed=verification.t_observed,
            measured_current=verification.measured_current,
            nominal_current=verification.nominal_current,
            defect_type_id=verification.defect_type_id,
            is_sticker_present=verification.is_sticker_present,
            is_test_ready=verification.is_test_ready,
            is_attention_required=verification.is_attention_required,
        )

        # Insert initial image links
        for link in image_links:
            await queries.upsert_verification_image_link(
                conn,
                verification_id=verification_id,
                image_id=link.image_id,
                is_deleted=link.is_deleted,
            )

        # Insert SUBMITTED event
        await queries.insert_verification_event(
            conn,
            verification_id=verification_id,
            event_type=VerificationEventType.SUBMITTED.value,
            inspector_id=verification.inspector_id,
            comment=None,
        )

        # Return created verification
        result = await self.get_by_id(conn, verification_id)
        if result is None:
            raise ValueError(f"Verification {verification_id} not found after create")
        return result

    async def update(
        self,
        conn,
        verification: Verification,
        current_verification: Verification,
        force: bool = False,
    ) -> Verification:
        """
        Update verification data and/or reassign verifier with optimistic concurrency control.
        Must be called within transaction.

        Args:
            conn: Database connection
            verification: Updated verification data
            current_verification: Current verification state from DB
            force: If True, ignore server_modified_at and mark extra image links as deleted

        Raises:
            ConcurrentModificationError: If concurrent modification detected (force=False)

        Returns:
            Updated verification
        """
        verification_id = verification.id
        new_server_modified_at = datetime.now(timezone.utc)

        if not (force or settings.disable_optimistic_locking):
            # Validate server_modified_at
            if verification.server_modified_at is None:
                raise ConcurrentModificationError(
                    ConflictError(
                        message="server_modified_at is required for updating existing verification",
                        server_modified_at=current_verification.server_modified_at,
                        conflicts=[
                            ConflictDetail(
                                field="server_modified_at",
                                message="Missing server_modified_at in request",
                            )
                        ],
                    )
                )

            if truncate_to_milliseconds(verification.server_modified_at) != truncate_to_milliseconds(
                current_verification.server_modified_at
            ):
                raise ConcurrentModificationError(
                    ConflictError(
                        message="Verification was modified by another client",
                        server_modified_at=current_verification.server_modified_at,
                        client_modified_at=verification.server_modified_at,
                        conflicts=[
                            ConflictDetail(
                                field="server_modified_at",
                                message="Timestamp mismatch",
                                server_value=current_verification.server_modified_at.isoformat(),
                                client_value=verification.server_modified_at.isoformat(),
                            )
                        ],
                    )
                )

            # Check for extra image links on server
            current_image_ids = {link.image_id for link in current_verification.image_links if not link.is_deleted}
            incoming_image_ids = {link.image_id for link in verification.image_links}
            extra_image_ids = current_image_ids - incoming_image_ids

            if extra_image_ids:
                raise ConcurrentModificationError(
                    ConflictError(
                        message="Extra child entities exist on server",
                        server_modified_at=current_verification.server_modified_at,
                        client_modified_at=verification.server_modified_at,
                        extra_child_ids=list(extra_image_ids),
                        conflicts=[
                            ConflictDetail(
                                field="image_links",
                                message=f"Server has {len(extra_image_ids)} extra image links not in client request",
                            )
                        ],
                    )
                )

        # Check if verifier changed
        verifier_changed = verification.verifier_id != current_verification.verifier_id

        # Update verification data
        await queries.update_verification(
            conn,
            id=verification_id,
            verifier_id=verification.verifier_id,
            server_modified_at=new_server_modified_at,
            step_type=verification.step_type,
            defect_id=verification.defect_id,
            unit_name=verification.unit_name,
            description=verification.description,
            is_resolved=verification.is_resolved,
            sticker_type_id=verification.sticker_type_id,
            t_sticker=verification.t_sticker,
            t_environment=verification.t_environment,
            t_similar_unit=verification.t_similar_unit,
            epsilon=verification.epsilon,
            t_observed=verification.t_observed,
            measured_current=verification.measured_current,
            nominal_current=verification.nominal_current,
            defect_type_id=verification.defect_type_id,
            is_sticker_present=verification.is_sticker_present,
            is_test_ready=verification.is_test_ready,
            is_attention_required=verification.is_attention_required,
        )

        # Sync image links
        await self._sync_image_links(conn, verification_id, verification.image_links, force)

        # Insert REASSIGNED event if verifier changed
        if verifier_changed:
            await queries.insert_verification_event(
                conn,
                verification_id=verification_id,
                event_type=VerificationEventType.REASSIGNED.value,
                inspector_id=verification.inspector_id,
                comment=None,
            )

        # Return updated verification
        result = await self.get_by_id(conn, verification_id)
        if result is None:
            raise ValueError(f"Verification {verification_id} not found after update")
        return result

    async def update_status(
        self,
        conn,
        verification_id: UUID,
        new_status: VerificationStatus,
        server_modified_at: datetime,
        inspector_id: int,
        comment: Optional[str] = None,
    ) -> Verification:
        """
        Update verification status (for review and resubmit operations).
        Must be called within transaction.

        Args:
            conn: Database connection
            verification_id: Verification ID
            new_status: New status to set
            server_modified_at: Expected server_modified_at (for concurrency check)
            inspector_id: ID of inspector performing the action
            comment: Optional comment (required for REJECTED)

        Raises:
            ConcurrentModificationError: If server_modified_at doesn't match

        Returns:
            Updated verification
        """
        current = await self.get_by_id(conn, verification_id)
        if current is None:
            raise ValueError(f"Verification {verification_id} not found")

        # Check server_modified_at
        if truncate_to_milliseconds(server_modified_at) != truncate_to_milliseconds(current.server_modified_at):
            raise ConcurrentModificationError(
                ConflictError(
                    message="Verification was modified since last read",
                    server_modified_at=current.server_modified_at,
                    client_modified_at=server_modified_at,
                    conflicts=[
                        ConflictDetail(
                            field="server_modified_at",
                            message="Timestamp mismatch - please reload and try again",
                            server_value=current.server_modified_at.isoformat(),
                            client_value=server_modified_at.isoformat(),
                        )
                    ],
                )
            )

        # Update status
        await queries.update_verification_status(conn, id=verification_id, status=new_status.value)

        # Bump server_modified_at
        new_server_modified_at = datetime.now(timezone.utc)
        await queries.bump_verification_server_modified_at(
            conn, id=verification_id, server_modified_at=new_server_modified_at
        )

        # Insert event
        event_type = {
            VerificationStatus.APPROVED: VerificationEventType.APPROVED,
            VerificationStatus.REJECTED: VerificationEventType.REJECTED,
            VerificationStatus.SUBMITTED: VerificationEventType.SUBMITTED,
        }[new_status]

        await queries.insert_verification_event(
            conn,
            verification_id=verification_id,
            event_type=event_type.value,
            inspector_id=inspector_id,
            comment=comment,
        )

        # Return updated verification
        result = await self.get_by_id(conn, verification_id)
        if result is None:
            raise ValueError(f"Verification {verification_id} not found after status update")
        return result

    async def copy_back_to_inspection_step(self, conn, verification: Verification, verified_at: datetime) -> None:
        """
        Copy approved verification data back to the original inspection step.
        Must be called within transaction.

        Args:
            conn: Database connection
            verification: Approved verification with data
            verified_at: Timestamp when verification was approved
        """
        # Update inspection step with verification data
        await queries.copy_back_to_inspection_step(
            conn,
            step_id=verification.inspection_step_id,
            step_type=verification.step_type,
            defect_id=verification.defect_id,
            unit_name=verification.unit_name,
            description=verification.description,
            is_resolved=verification.is_resolved,
            sticker_type_id=verification.sticker_type_id,
            t_sticker=verification.t_sticker,
            t_environment=verification.t_environment,
            t_similar_unit=verification.t_similar_unit,
            epsilon=verification.epsilon,
            t_observed=verification.t_observed,
            measured_current=verification.measured_current,
            nominal_current=verification.nominal_current,
            defect_type_id=verification.defect_type_id,
            is_sticker_present=verification.is_sticker_present,
            is_test_ready=verification.is_test_ready,
            is_attention_required=verification.is_attention_required,
            verified_by=verification.verifier_id,
            verified_at=verified_at,
        )

        # Delete existing inspection image links
        await queries.copy_back_inspection_image_links(conn, inspection_step_id=verification.inspection_step_id)

        # Insert verification image links into inspection step
        for link in verification.image_links:
            if not link.is_deleted:
                await queries.insert_inspection_image_link_from_verification(
                    conn,
                    inspection_step_id=verification.inspection_step_id,
                    image_id=link.image_id,
                    is_deleted=False,
                )

        # Get inspection_id from step to bump its server_modified_at
        step_data = await queries.get_inspection_step_data(conn, step_id=verification.inspection_step_id)
        if step_data:
            inspection_id = step_data["inspection_id"]
            await queries.bump_inspection_server_modified_at(
                conn, inspection_id=inspection_id, server_modified_at=datetime.now(timezone.utc)
            )

    async def _sync_image_links(
        self,
        conn,
        verification_id: UUID,
        image_links: list[VerificationImageLink],
        force: bool,
    ):
        """
        Synchronize verification image links: upsert all, mark removed as deleted.

        Args:
            conn: Database connection
            verification_id: Verification ID
            image_links: List of image links to sync
            force: If True, mark extra image links as deleted
        """
        # Get existing image link IDs for this verification
        existing_rows = [
            row async for row in queries.get_verification_image_link_ids(conn, verification_id=verification_id)
        ]
        existing_ids = {row["image_id"] for row in existing_rows}

        incoming_ids = {link.image_id for link in image_links}

        # Upsert all image links (add new or update existing)
        for link in image_links:
            await queries.upsert_verification_image_link(
                conn,
                verification_id=verification_id,
                image_id=link.image_id,
                is_deleted=link.is_deleted,
            )

        if force:
            # Mark removed image links as deleted
            to_delete = existing_ids - incoming_ids
            for image_id in to_delete:
                await queries.mark_verification_image_link_deleted(
                    conn, verification_id=verification_id, image_id=image_id
                )
