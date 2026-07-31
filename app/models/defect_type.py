"""DefectType aggregate models"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class DefectType(BaseModel):
    """DefectType aggregate"""

    id: int
    name: str
    short_name: str
    t_max: int
    t_excess: Optional[int] = None
    is_deleted: bool = False
    server_modified_at: datetime


class DefectTypeListResponse(BaseModel):
    """List of DefectType items"""

    items: list[DefectType]
