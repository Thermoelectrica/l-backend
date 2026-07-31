"""Inspector model"""

from datetime import datetime
from enum import Enum
from typing import List

from pydantic import BaseModel, Field


class AccessLevel(str, Enum):
    """
    Access level for inspectors.

    - READ: Can only perform GET operations
    - INSPECT: Can perform GET operations and add inspections/defects
    - MODIFY: Can perform all operations including claiming plants and modifying equipment
    """

    READ = "READ"
    INSPECT = "INSPECT"
    MODIFY = "MODIFY"


class Inspector(BaseModel):
    """Inspector aggregate (read-only reference data)"""

    id: int
    full_name: str
    username: str
    # Internal only - excluded from API responses to prevent disclosure
    access_level: AccessLevel = Field(default=AccessLevel.READ, exclude=True)
    is_deleted: bool = False
    server_modified_at: datetime


class InspectorListResponse(BaseModel):
    """List of Inspector items"""

    items: List[Inspector]
