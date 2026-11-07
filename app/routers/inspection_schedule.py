"""InspectionSchedule router"""

from datetime import datetime

from fastapi import APIRouter, Depends, Query

from app.constants import DEFAULT_MODIFIED_SINCE
from app.database import get_db_connection
from app.models.inspection_schedule import InspectionScheduleListResponse
from app.repositories.inspection_schedule import InspectionScheduleRepository

router = APIRouter(prefix="/inspection-schedule", tags=["inspection-schedule"])
inspection_schedule_repo = InspectionScheduleRepository()


@router.get("/all", response_model=InspectionScheduleListResponse)
async def get_all_inspection_schedules(
    modified_since: datetime = Query(
        DEFAULT_MODIFIED_SINCE,
        description="Only return inspection schedules modified after this timestamp",
    ),
    conn=Depends(get_db_connection),
):
    """Get all inspection schedules, optionally filtered by modification date"""
    schedules = await inspection_schedule_repo.get_all(conn, modified_since=modified_since)
    return InspectionScheduleListResponse(items=schedules)
