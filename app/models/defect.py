"""Defect aggregate models"""

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class DefectStatus(str, Enum):
    """Defect status enum"""

    DETECTED = "DETECTED"
    RESOLVED = "RESOLVED"


class Defect(BaseModel):
    """Defect aggregate root - read model"""

    id: UUID
    equipment_id: UUID
    unit_name: str
    defect_type_id: Optional[int] = None
    detected_at: datetime
    resolved_at: Optional[datetime] = None
    status: DefectStatus = DefectStatus.DETECTED
    is_deleted: bool = False
    server_modified_at: Optional[datetime] = None


# List models
class DefectListItem(BaseModel):
    """Lightweight defect item for list view"""

    id: UUID
    equipment_id: UUID
    unit_name: str
    defect_type_id: Optional[int] = None
    status: DefectStatus
    is_deleted: bool


class DefectListResponse(BaseModel):
    """Wrapped response for defect list with items key"""

    items: list[DefectListItem]
