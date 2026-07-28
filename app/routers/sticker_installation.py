"""Stisker_installation router - implements new API design principles"""

import logging
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from app.constants import DEFAULT_MODIFIED_SINCE
from app.database import get_db_connection
from app.dependencies.ownership import get_ownership_validator
from app.dependencies.permissions import get_permission_service
from app.exceptions import ConcurrentModificationError
from app.models.inspector import AccessLevel
from app.models.sticker_installation import StickerInstallaionListResponse, StickerInstallationModel
from app.repositories.sticker_installation import StickerInstallationRepository
from app.services.ownership_validator import OwnershipValidator
from app.services.permission_service import PermissionService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/sticker-installation", tags=["sticker-installation"])
sticker_installation_repo = StickerInstallationRepository()


@router.get("/all", response_model=StickerInstallaionListResponse)
async def get_all_stickers(
    modified_since: datetime = Query(
        DEFAULT_MODIFIED_SINCE,
        description="Only return inspections modified after this timestamp",
    ),
    conn=Depends(get_db_connection),
    permission_service: PermissionService = Depends(get_permission_service),
):
    """Get list of all stickers from DB"""

    all_stickers = await sticker_installation_repo.get_all(conn, modified_since=modified_since)
    return StickerInstallaionListResponse(items=all_stickers)


@router.get("/by_id/{sticker_id}", response_model=StickerInstallationModel)
async def get_sticker_by_id(
    sticker_id: UUID,
    conn=Depends(get_db_connection),
    permission_service: PermissionService = Depends(get_permission_service),
):
    """Get full sticker information by sticker id"""

    sticker = await sticker_installation_repo.get_by_id(conn, sticker_id)
    if not sticker:
        raise HTTPException(status_code=404, detail="Sticker not found")
    return sticker


@router.get("/by_plant_id/{plant_id}", response_model=list[StickerInstallationModel])
async def get_stickers_by_plant_id(
    plant_id: UUID,
    modified_since: datetime = Query(
        DEFAULT_MODIFIED_SINCE,
        description="Only return inspections modified after this timestamp",
    ),
    conn=Depends(get_db_connection),
    permission_service: PermissionService = Depends(get_permission_service),
):
    """Get all stickers information for plant by plant_id"""
    # Check plant access
    await permission_service.require_plant_access(plant_id)
    return await sticker_installation_repo.get_by_plant_id(conn, plant_id, modified_since=modified_since)


@router.put("", response_model=StickerInstallationModel)
async def upsert_sticker(
    sticker: StickerInstallationModel,
    force: bool = Query(
        default=False,
        description="If true, ignore server_modified_at and mark extra children as deleted",
    ),
    conn=Depends(get_db_connection),
    permission_service: PermissionService = Depends(get_permission_service),
    ownership_validator: OwnershipValidator = Depends(get_ownership_validator),
):
    """
    Create sticker installation.

    Rules:
    - force=false (default):
      - Validates that no immutable fields (e.g., inspector_id, control_point_id, kind, etc.)
        have changed for existing sticker
      - Rejects if such change is detected → returns 409 Conflict
      - Allows insert of new sticker with new id (no validation needed)
    - force=true:
      - Ignores validation of immutable fields (use with caution!)
      - Overwrites existing record regardless of field changes
    - Never allows "stealing" a sticker from another inspector (immutable inspector_id)
    - Permission: User must have INSPECT access level and access to the plant
    """
    try:
        async with conn.transaction():
            # Check access level (INSPECT required)
            permission_service.require_access_level(AccessLevel.INSPECT)

            # Check plant access via inspection
            plant_id = await permission_service.get_plant_id_from_inspector(sticker.inspector_id)  # type: ignore
            if plant_id:
                await permission_service.require_plant_access(plant_id)

            # Validate ownership before saving
            # development Не совсе понял, нужно ли тут что-то делать....
            # await ownership_validator.validate_inspection_ownership(sticker.inspector_id) # type: ignore

            result = await sticker_installation_repo.save(conn, sticker, force=force)
        return result
    except ConcurrentModificationError as e:
        logger.warning(
            "Concurrent modification detected for sticker installation",
            extra={
                "inspector_id": str(sticker.inspector_id),
                "conflict": e.conflict_error.model_dump(mode="json"),
            },
        )
        raise HTTPException(status_code=409, detail=e.conflict_error.model_dump(mode="json"))
    except ValueError as e:
        logger.warning(
            "Invalid sticker installation data",
            extra={"inspection_id": str(sticker.inspector_id), "error": str(e)},
        )
        raise HTTPException(status_code=400, detail=str(e))
