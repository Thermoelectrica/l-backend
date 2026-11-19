"""IESK inspection router - simplified inspections for plants listed in lesiv.iesk_plant"""

import logging
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from app.constants import DEFAULT_MODIFIED_SINCE
from app.database import get_db_connection
from app.dependencies.permissions import get_permission_service
from app.exceptions import ConcurrentModificationError
from app.models.iesk_inspection import IeskInspection, IeskInspectionListResponse
from app.models.inspector import AccessLevel
from app.repositories.iesk_inspection import IeskInspectionRepository
from app.services.permission_service import PermissionService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/iesk-inspection", tags=["iesk-inspection"])
iesk_inspection_repo = IeskInspectionRepository()


@router.get("/all", response_model=IeskInspectionListResponse)
async def get_all_iesk_inspections(
    modified_since: datetime = Query(
        DEFAULT_MODIFIED_SINCE,
        description="Only return IESK inspections modified after this timestamp",
    ),
    conn=Depends(get_db_connection),
    permission_service: PermissionService = Depends(get_permission_service),
):
    """Get all IESK inspections (lightweight list) from accessible plants, optionally filtered by modification date"""
    rows = await iesk_inspection_repo.get_all(conn, modified_since=modified_since)

    accessible_plant_ids = set(await permission_service.filter_accessible_plants(list({pid for pid, _ in rows})))
    return IeskInspectionListResponse(items=[item for pid, item in rows if pid in accessible_plant_ids])


@router.get("/by_id/{inspection_id}", response_model=IeskInspection)
async def get_iesk_inspection_by_id(
    inspection_id: UUID,
    conn=Depends(get_db_connection),
    permission_service: PermissionService = Depends(get_permission_service),
):
    """Get specific IESK inspection with image links"""
    plant_id = await permission_service.get_plant_id_from_iesk_inspection(inspection_id)
    if not plant_id:
        raise HTTPException(status_code=404, detail="IESK inspection not found")
    await permission_service.require_plant_access(plant_id)

    inspection = await iesk_inspection_repo.get_by_id(conn, inspection_id)
    if not inspection:
        raise HTTPException(status_code=404, detail="IESK inspection not found")
    return inspection


@router.get("/by_plant_id/{plant_id}", response_model=list[IeskInspection])
async def get_iesk_inspections_by_plant_id(
    plant_id: UUID,
    modified_since: datetime = Query(
        DEFAULT_MODIFIED_SINCE,
        description="Only return IESK inspections modified after this timestamp",
    ),
    conn=Depends(get_db_connection),
    permission_service: PermissionService = Depends(get_permission_service),
):
    """Get all IESK inspections for plant (full aggregates with image links),
    optionally filtered by modification date"""
    await permission_service.require_plant_access(plant_id)

    return await iesk_inspection_repo.get_by_plant_id(conn, plant_id, modified_since=modified_since)


@router.put("", response_model=IeskInspection)
async def upsert_iesk_inspection(
    inspection: IeskInspection,
    force: bool = Query(
        default=False,
        description="If true, ignore server_modified_at",
    ),
    conn=Depends(get_db_connection),
    permission_service: PermissionService = Depends(get_permission_service),
):
    """
    Create or replace IESK inspection with image links.

    Rules:
    - force=false (default):
      - Validates server_modified_at for existing inspection (409 on mismatch)
      - Ignores server_modified_at for new inspection
    - force=true:
      - Ignores server_modified_at validation
    - Image links missing from the request are marked as deleted (same as inspection image links)
    - Permission: INSPECT access level and access to the plant of the equipment
      (and to the plant the inspection currently belongs to, if it exists)
    - The plant type is not checked: the client decides which inspection to create from
      plant.external_plant_type. No plant claim is required.
    """
    try:
        async with conn.transaction():
            permission_service.require_access_level(AccessLevel.INSPECT)

            # Resolve the plant from the request body: for a new inspection there is nothing stored yet
            plant_id = await permission_service.get_plant_id_from_equipment(inspection.equipment_id)
            if not plant_id:
                raise ValueError(f"Equipment {inspection.equipment_id} not found")
            await permission_service.require_plant_access(plant_id)

            # An existing inspection must not be moved out of a plant the user has no access to
            current_plant_id = await permission_service.get_plant_id_from_iesk_inspection(inspection.id)
            if current_plant_id and current_plant_id != plant_id:
                await permission_service.require_plant_access(current_plant_id)

            result = await iesk_inspection_repo.save(conn, inspection, force=force)
        return result
    except ConcurrentModificationError as e:
        logger.warning(
            "Concurrent modification detected for IESK inspection",
            extra={
                "iesk_inspection_id": str(inspection.id),
                "conflict": e.conflict_error.model_dump(mode="json"),
            },
        )
        raise HTTPException(status_code=409, detail=e.conflict_error.model_dump(mode="json"))
    except ValueError as e:
        logger.warning(
            "Invalid IESK inspection data",
            extra={"iesk_inspection_id": str(inspection.id), "error": str(e)},
        )
        raise HTTPException(status_code=400, detail=str(e))
