"""EquipmentType router"""

from datetime import datetime

from fastapi import APIRouter, Depends, Query

from app.constants import DEFAULT_MODIFIED_SINCE
from app.database import get_db_connection
from app.models.equipment_type import EquipmentTypeListResponse
from app.repositories.equipment_type import EquipmentTypeRepository

router = APIRouter(prefix="/equipment-type", tags=["equipment-type"])
equipment_type_repo = EquipmentTypeRepository()


@router.get("/all", response_model=EquipmentTypeListResponse)
async def get_all_equipment_types(
    modified_since: datetime = Query(
        DEFAULT_MODIFIED_SINCE,
        description="Only return equipment types modified after this timestamp",
    ),
    conn=Depends(get_db_connection),
):
    """Get all equipment types with control point templates, optionally filtered by modification date"""
    equipment_types = await equipment_type_repo.get_all(conn, modified_since=modified_since)
    return EquipmentTypeListResponse(items=equipment_types)
