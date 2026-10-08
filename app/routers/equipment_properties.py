"""EquipmentProperties router - equipment attributes editable without a plant claim

Modifying equipment through PUT /equipment requires the caller's device to hold the pessimistic
claim on the whole plant. That is deliberately coarse for structural edits, but far too coarse for
a single attribute like the next inspection date: one user scheduling one piece of equipment would
lock everyone else out of the entire plant until the claim goes stale.

So these attributes are their own aggregate and this router performs no claim check - the same
reasoning that split defects out of the equipment aggregate (see app/routers/defect.py). Callers
still need plant access and INSPECT level to write.
"""

import logging
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from app.constants import DEFAULT_MODIFIED_SINCE
from app.database import get_db_connection
from app.dependencies.permissions import get_permission_service
from app.exceptions import ConcurrentModificationError
from app.models.equipment_properties import (
    EquipmentProperties,
    EquipmentPropertiesListResponse,
)
from app.models.inspector import AccessLevel
from app.repositories.equipment_properties import EquipmentPropertiesRepository
from app.services.permission_service import PermissionService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/equipment-properties", tags=["equipment-properties"])
equipment_properties_repo = EquipmentPropertiesRepository()


@router.get("/all", response_model=EquipmentPropertiesListResponse)
async def get_all_equipment_properties(
    modified_since: datetime = Query(
        DEFAULT_MODIFIED_SINCE,
        description="Only return equipment properties modified after this timestamp",
    ),
    conn=Depends(get_db_connection),
    permission_service: PermissionService = Depends(get_permission_service),
):
    """Get all equipment properties, filtered by modification date and accessible plants"""
    all_properties = await equipment_properties_repo.get_all(conn, modified_since=modified_since)

    # Filter to only properties from accessible plants.
    # The aggregate is keyed by equipment_id, so the existing equipment lookup resolves the plant.
    accessible_properties = []
    for properties in all_properties.items:
        plant_id = await permission_service.get_plant_id_from_equipment(properties.equipment_id)
        if plant_id and await permission_service.check_plant_access(plant_id):
            accessible_properties.append(properties)

    return EquipmentPropertiesListResponse(items=accessible_properties)


@router.get("/by_id/{equipment_id}", response_model=EquipmentProperties)
async def get_equipment_properties_by_id(
    equipment_id: UUID,
    conn=Depends(get_db_connection),
    permission_service: PermissionService = Depends(get_permission_service),
):
    """Get properties of a single equipment.

    Returns an all-default object for equipment that has no properties row yet, so the client never
    has to distinguish "not scheduled" from "never written". A 404 means the *equipment* is unknown.
    """
    plant_id = await permission_service.get_plant_id_from_equipment(equipment_id)
    if not plant_id:
        raise HTTPException(status_code=404, detail="Equipment not found")
    await permission_service.require_plant_access(plant_id)

    properties = await equipment_properties_repo.get_by_id(conn, equipment_id)
    if not properties:
        return EquipmentProperties(equipment_id=equipment_id)
    return properties


@router.get("/by_plant_id/{plant_id}", response_model=list[EquipmentProperties])
async def get_equipment_properties_by_plant_id(
    plant_id: UUID,
    modified_since: datetime = Query(
        DEFAULT_MODIFIED_SINCE,
        description="Only return equipment properties modified after this timestamp",
    ),
    conn=Depends(get_db_connection),
    permission_service: PermissionService = Depends(get_permission_service),
):
    """Get properties of all equipment on a plant, optionally filtered by modification date.

    Equipment without a properties row is omitted - there is nothing to sync for it.
    """
    # Check plant access
    await permission_service.require_plant_access(plant_id)

    return await equipment_properties_repo.get_by_plant_id(conn, plant_id, modified_since=modified_since)


@router.put("", response_model=EquipmentProperties)
async def upsert_equipment_properties(
    properties: EquipmentProperties,
    force: bool = Query(
        default=False,
        description="If true, ignore server_modified_at validation",
    ),
    conn=Depends(get_db_connection),
    permission_service: PermissionService = Depends(get_permission_service),
):
    """
    Create or replace the properties of one equipment.

    Rules:
    - force=false (default):
      - Validates server_modified_at for existing properties
      - Ignores server_modified_at when the equipment has no properties row yet
    - force=true:
      - Ignores server_modified_at validation

    Note: equipment properties are NOT owned by plant claims - that is the whole point of this
    aggregate. The plant does not have to be claimed, and a claim held by another device does not
    block the write. Callers still need INSPECT level and access to the plant.
    """
    try:
        async with conn.transaction():
            # Check access level (INSPECT required)
            permission_service.require_access_level(AccessLevel.INSPECT)

            # Check plant access via equipment. A missing plant_id means the equipment has not been
            # synced yet, which is allowed: the mobile client may push properties first.
            plant_id = await permission_service.get_plant_id_from_equipment(properties.equipment_id)
            if plant_id:
                await permission_service.require_plant_access(plant_id)

            result = await equipment_properties_repo.save(conn, properties, force=force)
        return result
    except ConcurrentModificationError as e:
        logger.warning(
            "Concurrent modification detected for equipment properties",
            extra={
                "equipment_id": str(properties.equipment_id),
                "conflict": e.conflict_error.model_dump(mode="json"),
            },
        )
        raise HTTPException(status_code=409, detail=e.conflict_error.model_dump(mode="json"))
    except ValueError as e:
        logger.warning(
            "Invalid equipment properties data",
            extra={"equipment_id": str(properties.equipment_id), "error": str(e)},
        )
        raise HTTPException(status_code=400, detail=str(e))
