"""FacilityTemplate router"""

from datetime import datetime

from fastapi import APIRouter, Depends, Query

from app.constants import DEFAULT_MODIFIED_SINCE
from app.database import get_db_connection
from app.models.facility_template import FacilityTemplateListResponse
from app.repositories.facility_template import FacilityTemplateRepository

router = APIRouter(prefix="/facility-template", tags=["facility-template"])
facility_template_repo = FacilityTemplateRepository()


@router.get("/all", response_model=FacilityTemplateListResponse)
async def get_all_facility_templates(
    modified_since: datetime = Query(
        DEFAULT_MODIFIED_SINCE,
        description="Only return facility templates modified after this timestamp",
    ),
    conn=Depends(get_db_connection),
):
    """Get all facility templates with equipment templates, optionally filtered by modification date"""
    facility_templates = await facility_template_repo.get_all(conn, modified_since=modified_since)
    return FacilityTemplateListResponse(items=facility_templates)
