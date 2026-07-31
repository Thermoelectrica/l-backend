"""EquipmentType aggregate models"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class ControlPointTemplate(BaseModel):
    """Control point template for equipment type"""

    id: int
    equipment_type_id: int
    name: str
    short_name: str
    default_sticker_id: Optional[int] = None
    is_deleted: bool = False


class EquipmentType(BaseModel):
    """EquipmentType aggregate with control point templates"""

    id: int
    name: str
    is_deleted: bool = False
    server_modified_at: datetime
    control_point_templates: list[ControlPointTemplate] = Field(default_factory=list)


class EquipmentTypeListResponse(BaseModel):
    """List of EquipmentType items"""

    items: list[EquipmentType]
