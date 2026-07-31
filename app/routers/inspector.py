"""Inspector router"""

from datetime import datetime

from fastapi import APIRouter, Depends, Query

from app.constants import DEFAULT_MODIFIED_SINCE
from app.database import get_db_connection
from app.models.inspector import InspectorListResponse
from app.repositories.inspector import InspectorRepository

router = APIRouter(prefix="/inspector", tags=["inspector"])
inspector_repo = InspectorRepository()


@router.get("/all", response_model=InspectorListResponse)
async def get_all_inspectors(
    modified_since: datetime = Query(
        DEFAULT_MODIFIED_SINCE,
        description="Only return inspectors modified after this timestamp",
    ),
    conn=Depends(get_db_connection),
):
    """Get all inspectors (read-only, without password_hash), optionally filtered by modification date"""
    inspectors = await inspector_repo.get_all(conn, modified_since=modified_since)
    return InspectorListResponse(items=inspectors)
