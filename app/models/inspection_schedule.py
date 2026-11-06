"""InspectionSchedule aggregate models"""

from datetime import datetime

from pydantic import BaseModel


class InspectionSchedule(BaseModel):
    """InspectionSchedule aggregate (read-only reference data)"""

    id: int
    name: str
    default_interval: int
    severity1_interval: int
    severity2_interval: int
    severity3_interval: int
    alert_interval: int
    is_deleted: bool = False
    server_modified_at: datetime


class InspectionScheduleListResponse(BaseModel):
    """List of InspectionSchedule items"""

    items: list[InspectionSchedule]
