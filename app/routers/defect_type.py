"""DefectType router"""

from datetime import datetime

from fastapi import APIRouter, Depends, Query

from app.constants import DEFAULT_MODIFIED_SINCE
from app.database import get_db_connection
from app.models.defect_type import DefectTypeListResponse
from app.repositories.defect_type import DefectTypeRepository

router = APIRouter(prefix="/defect-type", tags=["defect-type"])
defect_type_repo = DefectTypeRepository()


@router.get("/all", response_model=DefectTypeListResponse)
async def get_all_defect_types(
    modified_since: datetime = Query(
        DEFAULT_MODIFIED_SINCE,
        description="Only return defect types modified after this timestamp",
    ),
    conn=Depends(get_db_connection),
):
    """Get all defect types, optionally filtered by modification date"""
    defect_types = await defect_type_repo.get_all(conn, modified_since=modified_since)
    return DefectTypeListResponse(items=defect_types)
