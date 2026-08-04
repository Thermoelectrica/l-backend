"""Permission service for plant access and access level control"""

import logging
from typing import Optional
from uuid import UUID

import aiosql
import asyncpg
from aiosql.queries import Queries
from fastapi import HTTPException, status

from app.config import settings
from app.models.inspector import AccessLevel, Inspector
from app.utils.async_wrapper import AsyncWrapper

logger = logging.getLogger(__name__)

# Load SQL queries
_queries = aiosql.from_path("app/queries/permission.sql", settings.db_driver)
queries: Queries = AsyncWrapper(_queries) if settings.db_driver == "psycopg2" else _queries  # type: ignore[assignment]


# Access level hierarchy for comparison
ACCESS_LEVEL_HIERARCHY = {
    AccessLevel.READ: 0,
    AccessLevel.INSPECT: 1,
    AccessLevel.MODIFY: 2,
}


class PermissionService:
    """
    Centralized service for permission checking.
    Handles both plant access control and access level verification.
    """

    def __init__(self, conn: asyncpg.Connection, current_user: Inspector):
        """
        Initialize the permission service.

        Args:
            conn: Database connection to use for permission queries
            current_user: Current authenticated user
        """
        self.conn = conn
        self.current_user = current_user

    async def check_plant_access(self, plant_id: UUID) -> bool:
        """
        Check if current user has access to a specific plant.

        Args:
            plant_id: UUID of the plant to check

        Returns:
            True if user has access, False otherwise
        """
        # Anonymous user (when auth is disabled) has access to all plants
        if self.current_user.id == -1:
            return True

        result = await queries.check_plant_access(self.conn, inspector_id=self.current_user.id, plant_id=plant_id)
        return result["has_access"] if result else False

    async def require_plant_access(self, plant_id: UUID) -> None:
        """
        Require that current user has access to a plant.
        Raises 403 if access is denied.

        Args:
            plant_id: UUID of the plant to check

        Raises:
            HTTPException: 403 if user lacks access to the plant
        """
        if not await self.check_plant_access(plant_id):
            logger.warning(f"Access denied: inspector {self.current_user.id} attempted to access plant {plant_id}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"You do not have access to plant {plant_id}",
            )

    async def get_accessible_plant_ids(self) -> set[UUID]:
        """
        Get all plant IDs accessible to the current user.

        Returns:
            Set of plant UUIDs accessible to the user
        """
        # Anonymous user has access to all plants (handled at query level)
        if self.current_user.id == -1:
            return set()  # Empty set means "all plants" for anonymous user

        rows = []
        async for row in queries.get_accessible_plants(self.conn, inspector_id=self.current_user.id):
            rows.append(row)
        return {row["plant_id"] for row in rows}

    async def filter_accessible_plants(self, plant_ids: list[UUID]) -> list[UUID]:
        """
        Filter a list of plant IDs to only those accessible to current user.

        Args:
            plant_ids: List of plant UUIDs to filter

        Returns:
            Filtered list containing only accessible plant UUIDs
        """
        # Anonymous user has access to all plants
        if self.current_user.id == -1:
            return plant_ids

        accessible_ids = await self.get_accessible_plant_ids()
        return [pid for pid in plant_ids if pid in accessible_ids]

    async def get_plant_id_from_equipment(self, equipment_id: UUID) -> Optional[UUID]:
        """
        Get plant_id from equipment_id.

        Args:
            equipment_id: UUID of the equipment

        Returns:
            UUID of the plant, or None if not found
        """
        result = await queries.get_plant_from_equipment(self.conn, equipment_id=equipment_id)
        return result["plant_id"] if result else None

    async def get_plant_id_from_inspection(self, inspection_id: UUID) -> Optional[UUID]:
        """
        Get plant_id from inspection_id.

        Args:
            inspection_id: UUID of the inspection

        Returns:
            UUID of the plant, or None if not found
        """
        result = await queries.get_plant_from_inspection(self.conn, inspection_id=inspection_id)
        return result["plant_id"] if result else None

    async def get_plant_id_from_defect(self, defect_id: UUID) -> Optional[UUID]:
        """
        Get plant_id from defect_id.

        Args:
            defect_id: UUID of the defect

        Returns:
            UUID of the plant, or None if not found
        """
        result = await queries.get_plant_from_defect(self.conn, defect_id=defect_id)
        return result["plant_id"] if result else None

    async def get_plant_id_from_image(self, image_id: UUID) -> Optional[UUID]:
        """
        Get plant_id from image_id.

        Args:
            image_id: UUID of the image

        Returns:
            UUID of the plant, or None if not found
        """
        result = await queries.get_plant_from_image(self.conn, image_id=image_id)
        return result["plant_id"] if result else None

    async def get_plant_id_from_work_log(self, work_log_id: UUID) -> Optional[UUID]:
        """
        Get plant_id from work_log_id.

        Args:
            work_log_id: UUID of the work log

        Returns:
            UUID of the plant, or None if not found
        """
        result = await queries.get_plant_from_work_log(self.conn, work_log_id=work_log_id)
        return result["plant_id"] if result else None

    def check_access_level(self, required_level: AccessLevel) -> bool:
        """
        Check if current user has the required access level.

        Args:
            required_level: Minimum access level required

        Returns:
            True if user has sufficient access level, False otherwise
        """
        # Anonymous user (when auth is disabled) has all access
        if self.current_user.id == -1:
            return True

        user_level = ACCESS_LEVEL_HIERARCHY.get(self.current_user.access_level, 0)
        required_level_value = ACCESS_LEVEL_HIERARCHY.get(required_level, 0)

        return user_level >= required_level_value

    def require_access_level(self, required_level: AccessLevel) -> None:
        """
        Require that current user has the required access level.
        Raises 403 if access level is insufficient.

        Args:
            required_level: Minimum access level required

        Raises:
            HTTPException: 403 if user lacks required access level
        """
        if not self.check_access_level(required_level):
            logger.warning(
                f"Access denied: inspector {self.current_user.id} with level {self.current_user.access_level} "
                f"attempted operation requiring {required_level}"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access level {required_level.value} required."
                f" Your level: {self.current_user.access_level.value}",
            )

    async def grant_plant_access(self, plant_id: UUID) -> None:
        """
        Grant the current user access to a plant.
        This is typically called when a user creates a new plant.

        Args:
            plant_id: UUID of the plant to grant access to

        Note:
            Does nothing for anonymous users (id=-1)
        """
        # Skip for anonymous user
        if self.current_user.id == -1:
            return

        await queries.grant_plant_access(self.conn, inspector_id=self.current_user.id, plant_id=plant_id)
        logger.info(f"Granted plant access: inspector {self.current_user.id} -> plant {plant_id}")
