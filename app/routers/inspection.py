"""Inspection router - implements new API design principles"""

import logging
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from app.constants import DEFAULT_MODIFIED_SINCE
from app.database import get_db_connection
from app.dependencies.ownership import get_ownership_validator
from app.dependencies.permissions import get_permission_service
from app.exceptions import ConcurrentModificationError
from app.models.inspection import Inspection, InspectionListResponse
from app.models.inspector import AccessLevel
from app.repositories.inspection import InspectionRepository
from app.services.ownership_validator import OwnershipValidator
from app.services.permission_service import PermissionService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/inspection", tags=["inspection"])
inspection_repo = InspectionRepository()


@router.get("/all", response_model=InspectionListResponse)
async def get_all_inspections(
    modified_since: datetime = Query(
        DEFAULT_MODIFIED_SINCE,
        description="Only return inspections modified after this timestamp",
    ),
    conn=Depends(get_db_connection),
    permission_service: PermissionService = Depends(get_permission_service),
):
    """Get all inspection IDs (lightweight list), optionally filtered by modification date and accessible plants"""
    all_inspections = await inspection_repo.get_all(conn, modified_since=modified_since)

    # Filter to only inspections from accessible plants
    accessible_inspections = []
    for insp in all_inspections.items:
        plant_id = await permission_service.get_plant_id_from_inspection(insp.id)
        if plant_id and await permission_service.check_plant_access(plant_id):
            accessible_inspections.append(insp)

    return InspectionListResponse(items=accessible_inspections)


@router.get("/by_id/{inspection_id}", response_model=Inspection)
async def get_inspection_by_id(
    inspection_id: UUID,
    conn=Depends(get_db_connection),
    permission_service: PermissionService = Depends(get_permission_service),
):
    """Get specific inspection with steps and image links"""
    # Check plant access via inspection
    plant_id = await permission_service.get_plant_id_from_inspection(inspection_id)
    if not plant_id:
        raise HTTPException(status_code=404, detail="Inspection not found")
    await permission_service.require_plant_access(plant_id)

    inspection = await inspection_repo.get_by_id(conn, inspection_id)
    if not inspection:
        raise HTTPException(status_code=404, detail="Inspection not found")
    return inspection


@router.get("/by_plant_id/{plant_id}", response_model=list[Inspection])
async def get_inspections_by_plant_id(
    plant_id: UUID,
    modified_since: datetime = Query(
        DEFAULT_MODIFIED_SINCE,
        description="Only return inspections modified after this timestamp",
    ),
    conn=Depends(get_db_connection),
    permission_service: PermissionService = Depends(get_permission_service),
):
    """Get all inspections for plant (full aggregates with steps and image links),
    optionally filtered by modification date"""
    # Check plant access
    await permission_service.require_plant_access(plant_id)

    return await inspection_repo.get_by_plant_id(conn, plant_id, modified_since=modified_since)


@router.put("", response_model=Inspection)
async def upsert_inspection(
    inspection: Inspection,
    force: bool = Query(
        default=False,
        description="If true, ignore server_modified_at and mark extra children as deleted",
    ),
    conn=Depends(get_db_connection),
    permission_service: PermissionService = Depends(get_permission_service),
    ownership_validator: OwnershipValidator = Depends(get_ownership_validator),
):
    """
    Create or replace inspection with steps and image links.

    Rules:
    - force=false (default):
      - Validates server_modified_at for existing inspection
      - Rejects if extra child entities exist on server (409)
      - Ignores server_modified_at for new inspection
    - force=true:
      - Ignores server_modified_at validation
      - Marks extra child entities as deleted
    - Never allows "stealing" child entities from other inspections
    - Pessimistic lock: Only the user who created the inspection can modify it
    - Permission: User must have access to the plant
    """
    try:
        async with conn.transaction():
            # Check access level (INSPECT required)
            permission_service.require_access_level(AccessLevel.INSPECT)

            # Check plant access via inspection
            plant_id = await permission_service.get_plant_id_from_inspection(inspection.id)
            if plant_id:
                await permission_service.require_plant_access(plant_id)

            # Validate ownership before saving
            await ownership_validator.validate_inspection_ownership(inspection)
            result = await inspection_repo.save(conn, inspection, force=force)
        return result
    except ConcurrentModificationError as e:
        logger.warning(
            "Concurrent modification detected for inspection",
            extra={
                "inspection_id": str(inspection.id),
                "conflict": e.conflict_error.model_dump(mode="json"),
            },
        )
        raise HTTPException(status_code=409, detail=e.conflict_error.model_dump(mode="json"))
    except ValueError as e:
        logger.warning(
            "Invalid inspection data",
            extra={"inspection_id": str(inspection.id), "error": str(e)},
        )
        raise HTTPException(status_code=400, detail=str(e))
