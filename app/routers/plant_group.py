import logging
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from app.constants import DEFAULT_MODIFIED_SINCE
from app.database import get_db_connection
from app.dependencies.permissions import get_permission_service
from app.models.inspector import AccessLevel
from app.models.plant_group import PlantGroup, PlantGroupListResponse
from app.repositories.plant_group import PlantGroupRepository
from app.services.permission_service import PermissionService
from app.utils.db_utils import ConcurrentModificationError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/plant-group", tags=["plant", "plant_group"])
plant_group_repo = PlantGroupRepository()


@router.get("/all", response_model=PlantGroupListResponse)
async def get_all_groups(
    modified_since: datetime = Query(DEFAULT_MODIFIED_SINCE, description="Filter by modification date"),
    conn=Depends(get_db_connection),
) -> PlantGroupListResponse:
    """Получение списка групп (синхронизация)"""
    return await plant_group_repo.get_all(conn, modified_since=modified_since)


@router.get("/by_id/{group_id}", response_model=PlantGroup)
async def get_group(group_id: UUID, conn=Depends(get_db_connection)) -> PlantGroup:
    """Получение группы по ID"""
    group = await plant_group_repo.get_by_id(conn, group_id=group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    return group


@router.put("", response_model=PlantGroup)
async def upsert_group(
    group: PlantGroup,
    force: bool = Query(
        default=False,
        description="If true, ignore server_modified_at and force update",
    ),
    move_plants: bool = Query(
        default=False,
        description=(
            "If true, plants listed in plant_ids that already belong to another group "
            "will be moved to this group. If false (default), such plants cause a 400 error."
        ),
    ),
    conn=Depends(get_db_connection),
    permission_service: PermissionService = Depends(get_permission_service),
) -> PlantGroup:
    """
    Create or replace group with plant membership.

    Rules:
    - force=false (default):
      - Validates server_modified_at for existing groups
      - Rejects if modified_at doesn't match (409)
      - Ignores server_modified_at for new groups
    - force=true:
      - Ignores server_modified_at validation
      - Forces update even if concurrent modification detected
    - move_plants=false (default):
      - Rejects if any plant_id in the request already belongs to a different group (400)
    - move_plants=true:
      - Plants belonging to another group are moved to this group
    - Prevents cyclic dependencies when moving groups
    - Permission: User must have MODIFY access
    """
    try:
        async with conn.transaction():
            permission_service.require_access_level(AccessLevel.MODIFY)
            result = await plant_group_repo.save(conn, group, force=force, move_plants=move_plants)

        return result

    except ConcurrentModificationError as e:
        logger.warning(
            "Concurrent modification detected for group",
            extra={
                "group_id": str(group.id),
                "conflict": e.conflict_error.model_dump(mode="json"),
            },
        )
        raise HTTPException(status_code=409, detail=e.conflict_error.model_dump(mode="json"))
    except ValueError as e:
        logger.warning("Invalid group data", extra={"group_id": str(group.id), "error": str(e)})
        raise HTTPException(status_code=400, detail=str(e))
