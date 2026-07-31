"""Work log aggregate models"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class WorkLogInspector(BaseModel):
    """Work log - inspector relationship model"""

    inspector_id: int


class WorkLog(BaseModel):
    """Work log aggregate root - read model"""

    id: UUID
    started_at: datetime
    completed_at: Optional[datetime] = None
    installation_percentage: Optional[float] = Field(None, ge=0, le=100)
    inspector_id: int
    plant_id: UUID
    is_deleted: bool = False
    server_modified_at: Optional[datetime] = None
    duration_hours: Optional[float] = None
    inspectors: list[WorkLogInspector] = Field(default_factory=list)


class WorkLogListResponse(BaseModel):
    """Wrapped response for work log list with items key"""

    items: list[WorkLog]
