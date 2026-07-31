"""FacilityTemplate aggregate models"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class FacilityTemplateEquipment(BaseModel):
    """Equipment template for facility template"""

    id: int
    name: str
    is_container: bool = False
    equipment_type_id: Optional[int] = None
    parent_id: Optional[int] = None
    is_deleted: bool = False


class FacilityTemplate(BaseModel):
    """FacilityTemplate aggregate with equipment templates"""

    id: int
    name: str
    is_multiple_allowed: bool = False
    is_deleted: bool = False
    server_modified_at: datetime
    equipment_templates: list[FacilityTemplateEquipment] = Field(default_factory=list)


class FacilityTemplateListResponse(BaseModel):
    """List of FacilityTemplate items"""

    items: list[FacilityTemplate]
