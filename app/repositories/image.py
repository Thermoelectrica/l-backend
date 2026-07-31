"""Image repository"""

import json
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

import aiosql
from aiosql.queries import Queries

from app.config import settings
from app.constants import DEFAULT_MODIFIED_SINCE
from app.exceptions import ConcurrentModificationError
from app.models import ConflictDetail, ConflictError
from app.models.image import Image, ImageUploadStatus
from app.utils.async_wrapper import AsyncWrapper
from app.utils.datetime_utils import truncate_to_milliseconds

# Load queries from single file
_queries = aiosql.from_path("app/queries/image.sql", settings.db_driver)
queries: Queries = AsyncWrapper(_queries) if settings.db_driver == "psycopg2" else _queries  # type: ignore[assignment]


class ImageRepository:
    """Repository for Image aggregate"""

    async def get_by_id(self, conn, image_id: UUID) -> Optional[Image]:
        """Get image by ID"""
        row = await queries.get_by_id(conn, id=image_id)
        if row:
            # Parse JSONB metadata if it's a string
            row_dict = dict(row)
            if row_dict.get("metadata") and isinstance(row_dict["metadata"], str):
                row_dict["metadata"] = json.loads(row_dict["metadata"])
            return Image(**row_dict)
        return None

    async def get_by_plant_id(
        self, conn, plant_id: UUID, modified_since: datetime = DEFAULT_MODIFIED_SINCE
    ) -> list[Image]:
        """Get all images for a plant (joins through equipment and facility)"""
        rows = [row async for row in queries.get_by_plant_id(conn, plant_id=plant_id, modified_since=modified_since)]
        images = []
        for row in rows:
            row_dict = dict(row)
            if row_dict.get("metadata") and isinstance(row_dict["metadata"], str):
                row_dict["metadata"] = json.loads(row_dict["metadata"])
            images.append(Image(**row_dict))
        return images

    async def save(self, conn, image: Image, force: bool = False) -> Image:
        """
        Create or update image with optimistic concurrency control.
        Must be called within transaction.

        Args:
            conn: Database connection
            image: Image data to save
            force: If True, ignore server_modified_at validation

        Raises:
            ConcurrentModificationError: If concurrent modification detected (force=False)
            ValueError: If plant_id does not exist
        """
        image_id = image.id

        # Validate that plant_id exists
        result = await queries.plant_exists(conn, plant_id=image.plant_id)
        plant_exists = result["exists"] if result else False
        if not plant_exists:
            raise ValueError(f"Plant {image.plant_id} does not exist")

        # Get current state if exists
        current = await self.get_by_id(conn, image_id)

        # New server_modified_at timestamp
        new_server_modified_at = datetime.now(timezone.utc)

        if current and not (force or settings.disable_optimistic_locking):
            # Validate server_modified_at for existing image
            if image.server_modified_at is None:
                raise ConcurrentModificationError(
                    ConflictError(
                        message="server_modified_at is required for updating existing image",
                        server_modified_at=current.server_modified_at,
                        conflicts=[
                            ConflictDetail(
                                field="server_modified_at",
                                message="Missing server_modified_at in request",
                            )
                        ],
                    )
                )

            if truncate_to_milliseconds(image.server_modified_at) != truncate_to_milliseconds(
                current.server_modified_at
            ):
                raise ConcurrentModificationError(
                    ConflictError(
                        message="Image was modified by another client",
                        server_modified_at=current.server_modified_at,
                        client_modified_at=image.server_modified_at,
                        conflicts=[
                            ConflictDetail(
                                field="server_modified_at",
                                message="Timestamp mismatch",
                                server_value=current.server_modified_at.isoformat(),
                                client_value=image.server_modified_at.isoformat(),
                            )
                        ],
                    )
                )

        # Upsert image.
        # upload_status and server_uploaded_at are intentionally excluded from both
        # the INSERT column list and the ON CONFLICT DO UPDATE SET clause in the SQL,
        # so they are never overwritten by a PUT request:
        #   - INSERT: DB column defaults apply ('unknown' / NULL)
        #   - UPDATE: existing values are preserved untouched
        await queries.upsert(
            conn,
            id=image_id,
            plant_id=image.plant_id,
            original_file_name=image.original_file_name,
            image_type=image.image_type.value,
            metadata=json.dumps(image.metadata) if image.metadata else None,
            is_deleted=image.is_deleted,
            server_modified_at=new_server_modified_at,
        )

        result = await self.get_by_id(conn, image_id)
        if not result:
            raise ValueError(f"Image {image_id} not found after save")
        return result

    async def update_upload_status(
        self,
        conn,
        image_id: UUID,
        upload_status: ImageUploadStatus,
        server_uploaded_at: Optional[datetime],
    ) -> None:
        """Update upload status fields only (called by S3 event callback)."""
        await queries.update_upload_status(
            conn,
            id=image_id,
            upload_status=upload_status.value,
            server_uploaded_at=server_uploaded_at,
        )

    async def delete(self, conn, image_id: UUID) -> bool:
        """Delete image (actual delete, no is_deleted flag)"""
        await queries.delete(conn, id=image_id)
        return True
