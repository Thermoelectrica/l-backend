"""Permission dependencies for FastAPI endpoints"""

from typing import Callable, Optional
from uuid import UUID

import asyncpg
from fastapi import Depends, HTTPException, status

from app.database import get_db_connection
from app.dependencies.auth import get_current_user
from app.models.inspector import Inspector
from app.services.permission_service import PermissionService


def get_permission_service(
    conn: asyncpg.Connection = Depends(get_db_connection),
    current_user: Inspector = Depends(get_current_user),
) -> PermissionService:
    """
    Dependency to provide PermissionService instance.

    Args:
        conn: Database connection
        current_user: Current authenticated user

    Returns:
        PermissionService instance configured for current user
    """
    return PermissionService(conn, current_user)


def require_plant_access(plant_id: UUID):
    """
    Dependency factory that creates a dependency to check plant access.

    Usage:
        @router.get("/plant/by_id/{plant_id}")
        async def get_plant(
            plant_id: UUID,
            _: None = Depends(require_plant_access)
        ):
            ...

    Args:
        plant_id: UUID of the plant to check access for

    Returns:
        Dependency function that checks plant access
    """

    async def dependency(
        permission_service: PermissionService = Depends(get_permission_service),
    ) -> None:
        """Check plant access and raise 403 if denied"""
        await permission_service.require_plant_access(plant_id)

    return dependency


def require_plant_access_for_entity(entity_id: UUID, entity_type: str) -> Callable:
    """
    Dependency factory that creates a dependency to check plant access
    for entities that belong to a plant (equipment, inspection, defect, image).

    Usage:
        @router.get("/equipment/by_id/{equipment_id}")
        async def get_equipment(
            equipment_id: UUID,
            _: None = Depends(require_plant_access_for_entity(equipment_id, "equipment"))
        ):
            ...

    Args:
        entity_id: UUID of the entity (equipment, inspection, defect, or image)
        entity_type: Type of entity ("equipment", "inspection", "defect", or "image")

    Returns:
        Dependency function that resolves plant_id and checks access
    """

    async def dependency(
        permission_service: PermissionService = Depends(get_permission_service),
    ) -> None:
        """Resolve plant_id from entity and check access"""
        plant_id: Optional[UUID] = None

        if entity_type == "equipment":
            plant_id = await permission_service.get_plant_id_from_equipment(entity_id)
        elif entity_type == "inspection":
            plant_id = await permission_service.get_plant_id_from_inspection(entity_id)
        elif entity_type == "defect":
            plant_id = await permission_service.get_plant_id_from_defect(entity_id)
        elif entity_type == "image":
            plant_id = await permission_service.get_plant_id_from_image(entity_id)
        else:
            raise ValueError(f"Unknown entity type: {entity_type}")

        if plant_id is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"{entity_type.capitalize()} not found",
            )

        await permission_service.require_plant_access(plant_id)

    return dependency
