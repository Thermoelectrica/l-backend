"""Log model"""

from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class LogEntityType(str, Enum):
    """Log entity type enum"""

    INSPECTOR = "INSPECTOR"
    PLANT = "PLANT"
    FACILITY = "FACILITY"
    EQUIPMENT = "EQUIPMENT"
    INSPECTION = "INSPECTION"
    IMAGE = "IMAGE"


class LogOperation(str, Enum):
    """Log operation enum"""

    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"


class LogEntry(BaseModel):
    """Log entry model"""

    logged_at: datetime
    plant_id: Optional[UUID] = None
    inspector_id: int
    entity_id: str
    entity_type: LogEntityType
    op: LogOperation
    data: Optional[dict] = None
    message: str
